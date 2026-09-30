using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;

[assembly: AssemblyTitle("Cargo Track Setup")]
[assembly: AssemblyProduct("Cargo Track")]
[assembly: AssemblyVersion("1.0.5.0")]
[assembly: AssemblyFileVersion("1.0.5.0")]

internal static class Installer
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string installDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Cargo Track");
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string shortcutName = "Cargo Track";
            bool noShortcut = false, noLaunch = false, quiet = false;
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--install-dir" && i + 1 < args.Length) installDir = Path.GetFullPath(args[++i]);
                else if (args[i] == "--desktop-dir" && i + 1 < args.Length) desktopDir = Path.GetFullPath(args[++i]);
                else if (args[i] == "--shortcut-name" && i + 1 < args.Length) shortcutName = args[++i];
                else if (args[i] == "--no-shortcut") noShortcut = true;
                else if (args[i] == "--no-launch") noLaunch = true;
                else if (args[i] == "--quiet") quiet = true;
            }

            if (!quiet)
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                using (InstallOptions options = new InstallOptions(installDir, !noShortcut, !noLaunch))
                {
                    if (options.ShowDialog() != DialogResult.OK) return 0;
                    installDir = options.InstallPath;
                    noShortcut = !options.CreateDesktopShortcut;
                    noLaunch = !options.LaunchAfterInstall;
                }
            }
            string sourceZip = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "CargoTrack-1.0.5-Windows-x64.zip");
            string fullTarget = Path.GetFullPath(installDir);
            ValidateInstallTarget(fullTarget);
            string parent = Path.GetDirectoryName(fullTarget);
            Directory.CreateDirectory(parent);
            string stage = fullTarget + ".installing-" + Guid.NewGuid().ToString("N");
            Directory.CreateDirectory(stage);
            try
            {
                using (Stream fs = Assembly.GetExecutingAssembly().GetManifestResourceStream("CargoTrackPayload") ?? File.OpenRead(sourceZip))
                using (ZipArchive archive = new ZipArchive(fs, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string destination = Path.GetFullPath(Path.Combine(stage, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                        if (!destination.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("The package contains an invalid path.");
                        if (entry.FullName.EndsWith("/", StringComparison.Ordinal)) Directory.CreateDirectory(destination);
                        else
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(destination));
                            using (Stream input = entry.Open())
                            using (FileStream output = File.Create(destination)) input.CopyTo(output);
                        }
                    }
                }
                string exe = Path.Combine(stage, "CargoTrack", "CargoTrack.exe");
                if (!File.Exists(exe)) throw new InvalidDataException("The package is incomplete: CargoTrack.exe was not found.");
                string previous = fullTarget + ".previous-" + Guid.NewGuid().ToString("N");
                bool movedPrevious = false;
                try
                {
                    if (Directory.Exists(fullTarget)) { Directory.Move(fullTarget, previous); movedPrevious = true; }
                    Directory.Move(stage, fullTarget);
                    if (movedPrevious) Directory.Delete(previous, true);
                }
                catch
                {
                    if (!Directory.Exists(fullTarget) && movedPrevious && Directory.Exists(previous)) Directory.Move(previous, fullTarget);
                    throw;
                }
            }
            finally
            {
                if (Directory.Exists(stage)) Directory.Delete(stage, true);
            }

            string installedExe = Path.Combine(fullTarget, "CargoTrack", "CargoTrack.exe");
            if (!noShortcut) CreateShortcut(installedExe, desktopDir, shortcutName);
            if (!noLaunch) Process.Start(new ProcessStartInfo(installedExe) { UseShellExecute = true });
            if (!quiet) MessageBox.Show("Cargo Track was installed for this Windows user." + Environment.NewLine + fullTarget,
                "Cargo Track setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception ex)
        {
            if (Array.IndexOf(args, "--quiet") < 0) MessageBox.Show(ex.Message, "Cargo Track setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    internal static void ValidateInstallTarget(string path)
    {
        string target = Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
        if (target.Length == 0 || target.Equals(Path.GetPathRoot(path).TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Choose a dedicated Cargo Track folder, not a drive root.");
        if (File.Exists(target)) throw new ArgumentException("The installation path is a file.");
        if (!Directory.Exists(target)) return;
        string[] entries = Directory.GetFileSystemEntries(target);
        if (entries.Length == 0) return;
        if (!File.Exists(Path.Combine(target, "CargoTrack", "CargoTrack.exe")))
            throw new ArgumentException("Choose an empty folder or an existing Cargo Track installation folder.");
        foreach (string entry in entries)
        {
            string name = Path.GetFileName(entry);
            if (!name.Equals("CargoTrack", StringComparison.OrdinalIgnoreCase) && !name.Equals("README.txt", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("This folder contains other files. Choose a dedicated Cargo Track installation folder.");
        }
    }

    private static void CreateShortcut(string target, string desktop, string name)
    {
        Directory.CreateDirectory(desktop);
        if (name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) throw new ArgumentException("Invalid shortcut name");
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null) throw new InvalidOperationException("Windows shortcut support is unavailable.");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null,
            shell, new object[] { Path.Combine(desktop, name+".lnk") });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { Path.GetDirectoryName(target) });
        shortcutType.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { "Cargo Track cargo hand-off ledger" });
        shortcutType.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { target+",0" });
        shortcutType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
        Marshal.FinalReleaseComObject(shortcut);
        Marshal.FinalReleaseComObject(shell);
    }
}

internal sealed class InstallOptions : Form
{
    internal readonly TextBox PathInput = new TextBox();
    internal readonly CheckBox ShortcutOption = new CheckBox();
    internal readonly CheckBox LaunchOption = new CheckBox();
    internal readonly Button InstallButton = new Button();
    internal string InstallPath { get { return Path.GetFullPath(PathInput.Text.Trim()); } }
    internal bool CreateDesktopShortcut { get { return ShortcutOption.Checked; } }
    internal bool LaunchAfterInstall { get { return LaunchOption.Checked; } }

    internal InstallOptions(string initialPath, bool shortcut, bool launch)
    {
        Text = "Cargo Track setup";
        Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Font = new Font("Segoe UI", 11);
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(620, 280);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        Label heading = new Label { Text = "Install Cargo Track 1.0.5", AutoSize = true, Location = new Point(24, 20), Font = new Font(Font, FontStyle.Bold) };
        Label label = new Label { Text = "Installation folder", AutoSize = true, Location = new Point(24, 60) };
        PathInput.Text = initialPath; PathInput.SetBounds(24, 88, 450, 30); PathInput.AccessibleName = "Installation folder";
        Button browse = new Button { Text = "Browse…", Location = new Point(484, 86), Size = new Size(112, 34) };
        browse.Click += delegate {
            using (FolderBrowserDialog picker = new FolderBrowserDialog()) {
                picker.Description = "Choose a dedicated Cargo Track installation folder";
                if (Directory.Exists(PathInput.Text)) picker.SelectedPath = PathInput.Text;
                if (picker.ShowDialog(this) == DialogResult.OK) PathInput.Text = picker.SelectedPath;
            }
        };
        ShortcutOption.Text = "Create desktop shortcut"; ShortcutOption.Checked = shortcut;
        ShortcutOption.SetBounds(24, 134, 420, 28);
        LaunchOption.Text = "Launch Cargo Track after installation"; LaunchOption.Checked = launch;
        LaunchOption.SetBounds(24, 170, 520, 28);
        InstallButton.Text = "Install"; InstallButton.SetBounds(370, 224, 108, 36);
        InstallButton.Click += delegate {
            try { Installer.ValidateInstallTarget(InstallPath); DialogResult = DialogResult.OK; Close(); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "Choose installation folder", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        };
        Button cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Location = new Point(488, 224), Size = new Size(108, 36) };
        Controls.AddRange(new Control[] { heading, label, PathInput, browse, ShortcutOption, LaunchOption, InstallButton, cancel });
        AcceptButton = InstallButton; CancelButton = cancel;
    }
}
