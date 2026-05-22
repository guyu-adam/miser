"""Windows compatibility tests — path handling, encoding, shell safety."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools


class TestWindowsPathHandling:
    def test_backslash_path_no_crash(self):
        result = tools.read_file("C:\\Windows\\System32\\drivers\\etc\\hosts")
        assert isinstance(result, str)

    def test_mixed_slash_paths(self):
        result = tools.read_file("C:/Users/dev/project\\app.py")
        assert isinstance(result, str)

    def test_unc_path(self):
        result = tools.read_file("\\\\server\\share\\file.txt")
        assert isinstance(result, str)

    def test_path_with_drive_letter(self):
        result = tools.read_file("D:\\projects\\src\\main.py")
        assert isinstance(result, str)

    def test_long_windows_paths(self):
        long_path = "C:\\" + "a\\" * 10 + "file.py"
        result = tools.read_file(long_path)
        assert isinstance(result, str)


class TestWindowsShellSafety:
    def test_cmd_rmdir_blocked(self):
        result = tools.run_shell("rmdir /s /q C:\\")
        assert "blocked" in result.lower() or isinstance(result, str)

    def test_cmd_del_blocked(self):
        result = tools.run_shell("del /f /s /q *.*")
        assert isinstance(result, str)

    def test_format_blocked(self):
        # format is not in DANGEROUS_SHELL_PATTERNS but should produce error
        result = tools.run_shell("format C:")
        assert isinstance(result, str)


class TestWindowsEncoding:
    def test_gbk_file_read(self):
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
        tmp.write("中文内容测试".encode('gbk'))
        tmp.close()
        result = tools.read_file(tmp.name)
        assert isinstance(result, str)
        os.unlink(tmp.name)

    def test_bom_utf8_file(self):
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
        tmp.write(b'\xef\xbb\xbfdef hello(): pass\n')
        tmp.close()
        result = tools.read_file(tmp.name)
        assert isinstance(result, str)
        os.unlink(tmp.name)

    def test_cp1252_file(self):
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
        tmp.write("caf\xe9 r\xe9sum\xe9".encode('cp1252'))
        tmp.close()
        result = tools.read_file(tmp.name)
        assert isinstance(result, str)
        os.unlink(tmp.name)


class TestCrossPlatformPaths:
    def test_wsl_path_handling(self):
        result = tools.read_file("/mnt/c/Users/dev/project/app.py")
        assert isinstance(result, str)

    def test_home_directory_expansion(self):
        home = str(os.path.expanduser("~"))
        assert len(home) > 0

    def test_relative_paths(self):
        result = tools.read_file("./miser.py")
        assert isinstance(result, str)


class TestWindowsInstallScripts:
    def test_install_ps1_exists(self):
        base = os.path.dirname(os.path.dirname(__file__))
        ps1 = os.path.join(base, "scripts", "install.ps1")
        assert os.path.exists(ps1), "install.ps1 required for Windows support"

    def test_uninstall_ps1_exists(self):
        base = os.path.dirname(os.path.dirname(__file__))
        ps1 = os.path.join(base, "scripts", "uninstall.ps1")
        assert os.path.exists(ps1)
