from app.main import should_show_main_window


def test_manual_launch_is_visible_and_startup_is_explicitly_tray_only():
    assert should_show_main_window(startup=False,minimized=False,tray_available=True)
    assert not should_show_main_window(startup=True,minimized=False,tray_available=True)
    assert not should_show_main_window(startup=False,minimized=True,tray_available=True)
    # A machine without a tray must not leave a user with no way to reach UI.
    assert should_show_main_window(startup=True,minimized=False,tray_available=False)
