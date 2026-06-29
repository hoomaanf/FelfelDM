# ui/main_window.py - بخش‌های اصلاح‌شده
# (فایل کامل طولانی است، فقط بخش‌های تغییر یافته را نشان می‌دهم)

from ui.animated_dialog import AnimatedDialog


def _show_add_dialog(self) -> None:
    """Show the Add Download dialog with animation."""
    dialog = AddDownloadDialog(
        self.queue_controller.get_queues(),
        self.store,
        self.queue_controller.current_index,
        self
    )
    # Use animated dialog wrapper
    animated_dialog = AnimatedDialog(self)
    animated_dialog.set_content_widget(dialog)
    animated_dialog.setWindowTitle("Add Downloads")
    if animated_dialog.exec():
        urls = dialog.get_urls()
        queue_idx = dialog.get_queue_index()
        options = dialog.get_options()
        if urls:
            self.download_controller.add_urls(urls, queue_idx, options)


def _show_add_torrent_dialog(self) -> None:
    """Show the Add Torrent dialog with animation."""
    dialog = AddTorrentDialog(
        self.queue_controller.get_queues(),
        self.store,
        self.queue_controller.current_index,
        self
    )
    animated_dialog = AnimatedDialog(self)
    animated_dialog.set_content_widget(dialog)
    animated_dialog.setWindowTitle("Add Torrent")
    if animated_dialog.exec():
        torrent_path = dialog.get_torrent_path()
        queue_idx = dialog.get_queue_index()
        options = dialog.get_options()
        if torrent_path:
            # ... ادامه کد
            pass


def _show_settings(self) -> None:
    """Show the Settings dialog with animation."""
    dialog = SettingsDialog(self.store, self)
    animated_dialog = AnimatedDialog(self)
    animated_dialog.set_content_widget(dialog)
    animated_dialog.setWindowTitle("Settings")
    if animated_dialog.exec():
        self._apply_theme_from_settings()
