"""Adding downloads: drag & drop, the add dialog, rule matching."""

import os
import uuid
from typing import Dict, List, Optional

from PyQt6.QtCore import QMimeData, QTimer, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from core.rule_engine import expand_path
from ui.dialogs import AddDownloadDialog
from ui.widgets import DropOverlay


class AddDownloadMixin:
    """Adding downloads: drag & drop, the add dialog, rule matching."""

    # ═══════════════════════════════════════════════════════════════
    # Drag & Drop
    # ═══════════════════════════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drags that carry URLs (links, text, or local files)."""
        urls = self._extract_urls_from_mime(event.mimeData())
        if urls:
            event.acceptProposedAction()
            self._set_drop_highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._extract_urls_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_highlight(False)
        urls = self._extract_urls_from_mime(event.mimeData())
        if not urls:
            event.ignore()
            return
        event.acceptProposedAction()
        self._handle_dropped_urls(urls)

    def _extract_urls_from_mime(self, mime: QMimeData) -> list:
        """Extract download URLs from a drag-and-drop payload.

        Handles both text/uri-list (Firefox/Chrome link drags, file:// drops)
        and text/plain (some browsers only provide this). Returns an ordered,
        de-duplicated list of URLs.
        """
        urls = []

        if mime.hasUrls():
            for url in mime.urls():
                s = url.toString().strip()
                if not s:
                    continue
                if s.startswith("file://"):
                    # Local file drop — keep the local path so the user can
                    # see what they dropped, but only if it's a .txt we can
                    # parse. Otherwise, skip it.
                    local = url.toLocalFile()
                    if local and local.lower().endswith(".txt"):
                        try:
                            with open(local, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line and line.lower().startswith(
                                        (
                                            "http://",
                                            "https://",
                                            "ftp://",
                                            "ftps://",
                                            "magnet:",
                                        )
                                    ):
                                        urls.append(line)
                        except Exception as e:
                            print(f"⚠️ [Drop] Could not read {local}: {e}")
                    continue
                urls.append(s)

        if not urls and mime.hasText():
            text = mime.text().strip()
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith(
                    ("http://", "https://", "ftp://", "ftps://", "magnet:")
                ):
                    urls.append(line)

        # De-dup while preserving order
        seen = set()
        result = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    def _handle_dropped_urls(self, urls: list) -> None:
        """Open the Add Download dialog pre-filled with dropped URLs.

        Works the same way as the extension handler: if the dialog is
        already open, the URLs are appended to it.
        """
        if not urls:
            return

        self._open_or_update_add_dialog(urls)
        self.status_label.setText(f"📥 {len(urls)} URL(s) dropped")

    def _set_drop_highlight(self, on: bool) -> None:
        """Show/hide a subtle overlay over the downloads table only."""
        if on:
            if self._drop_overlay is None:
                # Parent is the table's viewport, so the overlay stays
                # exactly over the rows area (not on toolbar/sidebar/menu).
                self._drop_overlay = DropOverlay(self.table.viewport())
            self._drop_overlay.setGeometry(self.table.viewport().rect())
            self._drop_overlay.show()
            self._drop_overlay.raise_()
            self._drop_overlay.update()
        else:
            if self._drop_overlay is not None:
                self._drop_overlay.hide()

    def _open_or_update_add_dialog(self, urls: List[str] = None) -> None:
        key = "add_download"
        existing = self._open_dialogs.get(key)

        if existing is not None:
            try:
                if existing.isVisible():
                    if urls:
                        current = existing.url_edit.toPlainText().strip()
                        existing_set = set(
                            line.strip() for line in current.split("\n") if line.strip()
                        )
                        fresh = [u for u in urls if u not in existing_set]
                        if fresh:
                            combined = (
                                f"{current}\n" + "\n".join(fresh)
                                if current
                                else "\n".join(fresh)
                            )
                            existing.url_edit.setPlainText(combined)

                    # Defer the raise until after the layout pass triggered
                    # by setPlainText → textChanged → resize has finished.
                    QTimer.singleShot(0, lambda w=existing: self._force_raise_dialog(w))
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        all_queues = self.store.queues
        dlg = AddDownloadDialog(all_queues, 0, self)

        if urls:
            dlg.url_edit.setPlainText("\n".join(urls))
        else:
            clip = QApplication.clipboard().text().strip()
            if clip:
                valid_lines = [
                    line.strip()
                    for line in clip.split("\n")
                    if line.strip().startswith(("http", "magnet:", "ftp"))
                ]
                if valid_lines:
                    dlg.url_edit.setPlainText("\n".join(valid_lines))

        self._show_singleton_dialog(
            key, dlg, on_accepted=self._process_add_download_common
        )

    def _force_raise_dialog(self, dlg) -> None:
        """Bring a dialog to the front, even if minimized or unfocused.

        On KDE/Wayland, raise_()/activateWindow() alone don't reliably
        bring a dialog to the front when another window has focus. Adding
        WindowStaysOnTopHint temporarily forces the WM to surface it, then
        we restore the original flags.
        """
        try:
            # Remember the original flags
            original_flags = dlg.windowFlags()

            # Force the dialog on top of everything (works around
            # focus-stealing-prevention on KDE/Wayland)
            dlg.setWindowFlags(original_flags | Qt.WindowType.WindowStaysOnTopHint)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

            # Restore the original flags after a short delay so the dialog
            # doesn't stay pinned above every other window forever.
            def _restore():
                try:
                    dlg.setWindowFlags(original_flags)
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
                except RuntimeError:
                    pass

            QTimer.singleShot(300, _restore)
        except RuntimeError:
            pass

    def _show_singleton_dialog(self, key: str, dlg: QDialog, on_accepted=None) -> None:
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                pass
            self._open_dialogs.pop(key, None)

        self._open_dialogs[key] = dlg
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        def _cleanup():
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        def _handle_accepted():
            try:
                if on_accepted:
                    on_accepted(dlg)
            finally:
                _cleanup()

        dlg.accepted.connect(_handle_accepted)
        dlg.rejected.connect(_cleanup)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _rules_with_size_conditions(self) -> bool:
        """True when at least one enabled rule constrains file size.

        Only then is it worth paying for an extra HEAD request when adding
        a download.
        """
        try:
            for rule in self.store.rule_engine.rules:
                if rule.enabled and (rule.size_min > 0 or rule.size_max > 0):
                    return True
        except Exception:
            pass
        return False

    def _probe_size_for_rules(self, url: str, proxy_dict=None) -> Optional[int]:
        """Best-effort file size lookup used only to evaluate size rules.

        Fully optional: a bounded HEAD request, and any failure means the
        size conditions are simply not evaluated for this URL.
        """
        try:
            from core.file_size_fetcher import FileSizeFetcher

            fetcher = FileSizeFetcher(timeout=5, proxy=proxy_dict)
            try:
                size = fetcher.get_size(url)
            finally:
                fetcher.close()
            if size and size > 0:
                return int(size)
        except Exception as e:
            print(f"⚠️ [Rules] Size probe failed for {url[:60]}: {e}")
        return None

    def _process_add_download_common(self, dlg: "AddDownloadDialog") -> None:
        """Unified handler for both Quick Download and Add to Queue."""
        d = dlg.get_data()
        if not d["urls"]:
            return

        queue_name = d.get("queue_name", "__direct__")
        target_queue = self._get_or_create_queue(queue_name)

        self._apply_settings_to_aria2()

        user_connections = int(d.get("connections") or 8)

        options = {
            "dir": d["path"],
            "split": str(user_connections),
            "max-connection-per-server": str(user_connections),
            "min-split-size": "1M",
            "stream-piece-selector": "geom",
            "continue": "true",
            "always-resume": "true",
            "header": [
                "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
            ],
        }

        proxy_mode = d.get("proxy_mode", 0)
        if proxy_mode == 0:
            proxy = self.proxy_manager.get_proxy_for_queue(queue_name)
            if proxy and proxy.is_valid():
                options["all-proxy"] = proxy._build_proxy_url()
        elif proxy_mode == 1:
            custom_proxy = d.get("custom_proxy")
            if custom_proxy and custom_proxy.is_valid():
                options["all-proxy"] = custom_proxy._build_proxy_url()
        elif proxy_mode == 2:
            options["all-proxy"] = ""

        is_direct = queue_name == "__direct__"
        added = 0
        new_gids = []
        # Same-queue duplicates that were blocked.
        skipped_duplicates: list = []  # [(url, queue_name)]
        # Cross-queue duplicates that were ALLOWED but reported.
        cross_queue_added: list = []  # [(url, existing_queue_names)]
        failed_urls: list = []  # [(url, reason)]

        print(f"📂 [Add] Queue: {queue_name}")
        print(f"📂 [Add] Save path: {d['path']!r}")
        print(f"📂 [Add] URLs: {len(d['urls'])}")

        # url → set of queue names it currently lives in.
        # Per-queue duplicate policy:
        #   - same queue      → block (cannot add twice to one queue)
        #   - different queue → allow, but mention in notification
        existing_urls: Dict[str, set] = {}
        for q in self.store.queues:
            for dl_id, dl_info in q.downloads_info.items():
                u = dl_info.get("url")
                if u:
                    existing_urls.setdefault(u, set()).add(q.name)

        rules_need_size = self._rules_with_size_conditions()

        for url in d["urls"]:

            # ── Resolve rules first (they may redirect the queue) ──
            rule_size = None
            if rules_need_size:
                rule_size = self._probe_size_for_rules(
                    url,
                    options.get("all-proxy")
                    and {
                        "http": options["all-proxy"],
                        "https": options["all-proxy"],
                    },
                )

            rule = self.store.rule_engine.find_match(url, rule_size)

            url_options = options.copy()
            url_queue = target_queue
            url_path = d["path"]
            url_connections = user_connections
            url_speed_limit = getattr(target_queue, "speed_limit", 0)

            is_schedule_active = (
                url_queue.schedule_enabled and url_queue.is_scheduled_now()
            )

            if rule:
                if rule.queue:
                    for q in self.store.queues:
                        if q.name == rule.queue:
                            url_queue = q
                            break
                    else:
                        url_queue = self._get_or_create_queue(rule.queue)

                if rule.folder:
                    url_path = expand_path(rule.folder)

                if rule.connections:
                    url_connections = rule.connections
                    url_options["split"] = str(rule.connections)
                    url_options["max-connection-per-server"] = str(rule.connections)

                if rule.speed_limit:
                    url_speed_limit = rule.speed_limit

                url_options["dir"] = url_path

                print(
                    f"[Rules] '{rule.name}' matched for {url[:50]}... "
                    f"queue='{url_queue.name}', folder='{url_path}', "
                    f"conn={url_connections}, speed={url_speed_limit}"
                )

            # ── Duplicate check (per-queue policy, no dialog) ──
            # Runs AFTER url_queue is final.
            #   same queue  → block silently
            #   other queue → allow, remember for the final notification
            existing_queues = existing_urls.get(url, set())

            if url_queue.name in existing_queues:
                print(
                    f"[Add] Blocked same-queue duplicate in "
                    f"'{url_queue.name}': {url!r}"
                )
                skipped_duplicates.append((url, url_queue.name))
                continue

            if existing_queues:
                print(
                    f"[Add] Cross-queue duplicate allowed: {url!r} "
                    f"(already in {existing_queues}, adding to '{url_queue.name}')"
                )
                cross_queue_added.append((url, sorted(existing_queues)))
                # Falls through — no continue, so it gets added.

            url_is_direct = url_queue.name == "__direct__"
            if not url_is_direct and url_queue.paused and not is_schedule_active:
                url_options["pause"] = "true"

            # ── Submit to aria2 ──
            gid = self.aria2.add_url(url, url_options)
            if not gid:
                print(f"[Add] aria2.add_url returned None for URL: {url!r}")
                failed_urls.append((url, "aria2 rejected the URL"))
                continue

            existing_urls.setdefault(url, set()).add(url_queue.name)

            download_id = uuid.uuid4().hex[:16]

            url_queue.downloads.append(download_id)

            clean_name = self._extract_filename(url)
            full_path = os.path.join(url_path, clean_name)

            if url_is_direct or not url_queue.paused or is_schedule_active:
                initial_status = "active"
                if is_schedule_active and url_queue.paused:
                    url_queue.paused = False
                    url_queue.manually_paused = False
            else:
                initial_status = "paused"

            common_fields = {
                "id": download_id,
                "aria2_gid": gid,
                "url": url,
                "name": clean_name,
                "totalLength": 0,
                "completedLength": 0,
                "status": initial_status,
                "files": [{"path": full_path}],
                "category": "📁 Other",
                "download_type": "normal",
                "save_path": url_path,
                "matched_rule": rule.name if rule else None,
                "rule_speed_limit": (
                    rule.speed_limit if rule and rule.speed_limit else 0
                ),
                "speed_limit": 0,
                "proxy_url": url_options.get("all-proxy", ""),
                "connections": url_connections,
                "min_split_size": url_options.get("min-split-size", "1M"),
                "stream_piece_selector": url_options.get(
                    "stream-piece-selector", "geom"
                ),
                "header": url_options.get("header", []),
            }

            url_queue.downloads_info[download_id] = dict(common_fields)

            runtime_fields = dict(common_fields)
            runtime_fields.update(
                {
                    "downloadSpeed": 0,
                    "connections": 0,
                    "errorMessage": "",
                    "size_fetch_attempts": 0,
                }
            )
            self._all_downloads[download_id] = runtime_fields

            if is_schedule_active:
                try:
                    status = self.aria2.get_status(gid)
                    if status and status.get("status") in ("paused", "waiting"):
                        self.worker.resume_requested.emit(gid)
                except Exception as e:
                    print(f"Could not resume {download_id}: {e}")

            per_download_speed = self._to_int(d.get("per_download_speed", 0))
            if per_download_speed > 0:
                self._all_downloads[download_id]["speed_limit"] = per_download_speed
                url_queue.downloads_info[download_id][
                    "speed_limit"
                ] = per_download_speed
                self._worker_set_speed_limit(download_id, per_download_speed)
            else:
                final_speed = url_speed_limit or getattr(url_queue, "speed_limit", 0)
                if final_speed > 0:
                    self._worker_set_speed_limit(download_id, final_speed)

            new_gids.append(download_id)
            added += 1

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        if is_direct:
            for download_id in new_gids:
                try:
                    dl = self._all_downloads.get(download_id, {})
                    aria2_gid = dl.get("aria2_gid")
                    if not aria2_gid:
                        continue

                    status = self.aria2.get_status(aria2_gid)
                    if status and status.get("status") in ("waiting", "paused"):
                        self.worker.resume_requested.emit(aria2_gid)
                except Exception as e:
                    print(f"⚠️ Could not resume {download_id}: {e}")
            self.store.save()

            for download_id in new_gids:
                QTimer.singleShot(
                    300,
                    lambda did=download_id: self._open_progress_dialog(did),
                )

        # ── Notification ──
        n_same = len(skipped_duplicates)
        n_cross = len(cross_queue_added)
        n_failed = len(failed_urls)

        if added == 0:
            if n_same > 0 and n_failed == 0:
                if n_same == 1:
                    qname = skipped_duplicates[0][1]
                    msg = (
                        f"⏭This URL is already in queue '{qname}'.\n"
                        f"Nothing was added."
                    )
                else:
                    msg = (
                        f"⏭All {n_same} URL(s) are already in the "
                        f"selected queue.\nNothing was added."
                    )
                icon = QSystemTrayIcon.MessageIcon.Warning

            elif n_failed > 0 and n_same == 0:
                msg = f"Could not add {n_failed} URL(s) — aria2 rejected them."
                icon = QSystemTrayIcon.MessageIcon.Critical

            else:
                parts = []
                if n_same:
                    parts.append(f"{n_same} already in this queue")
                if n_failed:
                    parts.append(f"{n_failed} failed")
                msg = f"Nothing added — {', '.join(parts)}."
                icon = QSystemTrayIcon.MessageIcon.Warning

        else:
            if is_direct:
                base = f"Added {added} download(s) to Direct Downloads (started)"
            elif target_queue.paused:
                base = f"Added {added} download(s) to '{target_queue.name}' (paused)"
            else:
                base = (
                    f"Added {added} download(s) to '{target_queue.name}' (downloading)"
                )

            extras = []
            if n_cross > 0:
                # Show which queue(s) already had it, so the user knows
                # a second copy is being downloaded.
                if n_cross == 1:
                    _, qlist = cross_queue_added[0]
                    qstr = ", ".join(f"'{x}'" for x in qlist)
                    extras.append(f"already existed in {qstr} — added anyway")
                else:
                    all_queues = sorted({q for _, ql in cross_queue_added for q in ql})
                    qstr = ", ".join(f"'{x}'" for x in all_queues)
                    extras.append(
                        f"{n_cross} URL(s) already existed in {qstr} — added anyway"
                    )
            if n_same > 0:
                extras.append(f"{n_same} already in this queue (skipped)")
            if n_failed > 0:
                extras.append(f"{n_failed} failed")

            msg = base + ("\n" + "\n".join(extras) if extras else "")
            icon = (
                QSystemTrayIcon.MessageIcon.Information
                if not extras
                else QSystemTrayIcon.MessageIcon.Warning
            )

        self.tray.showMessage("FelfelDM", msg, icon, 10000)

        self._refresh_table()

    def _add_download(self) -> None:
        """Open the unified Add Download dialog (toolbar / Ctrl+N / Ctrl+U)."""
        self._open_or_update_add_dialog()

    def _extract_filename(self, url: str) -> str:

        try:
            raw_name = url.split("/")[-1]
            clean_name = raw_name.split("?")[0] if "?" in raw_name else raw_name
            clean_name = clean_name.strip()
        except Exception:
            return "Unknown"

        # Reject dangerous or useless results.
        if not clean_name:
            return "Unknown"
        if clean_name in (".", ".."):
            return "Unknown"
        if "/" in clean_name or "\\" in clean_name:
            return "Unknown"
        # Reject Windows-reserved characters too, just for safety.
        if any(ch in clean_name for ch in '<>:"|*'):
            return "Unknown"

        return clean_name

    def _parse_speed(self, speed_str: str) -> int:
        if not speed_str:
            return 0
        try:
            speed_str = speed_str.strip()
            if "KiB/s" in speed_str:
                return int(float(speed_str.replace("KiB/s", "").strip()) * 1024)
            if "MiB/s" in speed_str:
                return int(float(speed_str.replace("MiB/s", "").strip()) * 1024 * 1024)
            if "KB/s" in speed_str:
                return int(float(speed_str.replace("KB/s", "").strip()) * 1000)
            if "MB/s" in speed_str:
                return int(float(speed_str.replace("MB/s", "").strip()) * 1000 * 1000)
            if speed_str.isdigit():
                return int(speed_str)
            return 0
        except Exception:
            return 0
