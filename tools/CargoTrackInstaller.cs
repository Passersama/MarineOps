using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;

[assembly: AssemblyTitle("MarineOps Setup")]
[assembly: AssemblyProduct("MarineOps")]
[assembly: AssemblyVersion("1.2.6.0")]
[assembly: AssemblyFileVersion("1.2.6.0")]

internal static class Installer
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string installDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "MarineOps");
            string legacyDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Cargo Track");
            if (!Directory.Exists(installDir) && File.Exists(Path.Combine(legacyDir, "CargoTrack", "CargoTrack.exe"))) installDir = legacyDir;
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string shortcutName = "MarineOps";
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
            string sourceZip = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "MarineOps-1.2.6-Windows-x64.zip");
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
                string exe = Path.Combine(stage, "MarineOps", "MarineOps.exe");
                if (!File.Exists(exe)) throw new InvalidDataException("The package is incomplete: MarineOps.exe was not found.");
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

            string installedExe = Path.Combine(fullTarget, "MarineOps", "MarineOps.exe");
            if (!noShortcut) CreateShortcut(installedExe, desktopDir, shortcutName);
            if (!noLaunch) Process.Start(new ProcessStartInfo(installedExe) { UseShellExecute = true });
            if (!quiet) MessageBox.Show("MarineOps was installed for this Windows user." + Environment.NewLine + fullTarget,
                "MarineOps setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception ex)
        {
            if (Array.IndexOf(args, "--quiet") < 0) MessageBox.Show(ex.Message, "MarineOps setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    internal static void ValidateInstallTarget(string path)
    {
        string target = Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
        if (target.Length == 0 || target.Equals(Path.GetPathRoot(path).TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Choose a dedicated MarineOps folder, not a drive root.");
        if (File.Exists(target)) throw new ArgumentException("The installation path is a file.");
        if (!Directory.Exists(target)) return;
        string[] entries = Directory.GetFileSystemEntries(target);
        if (entries.Length == 0) return;
        bool current = File.Exists(Path.Combine(target, "MarineOps", "MarineOps.exe"));
        bool legacy = File.Exists(Path.Combine(target, "CargoTrack", "CargoTrack.exe"));
        if (!current && !legacy)
            throw new ArgumentException("Choose an empty folder or an existing MarineOps installation folder.");
        foreach (string entry in entries)
        {
            string name = Path.GetFileName(entry);
            if (!name.Equals("MarineOps", StringComparison.OrdinalIgnoreCase) && !name.Equals("CargoTrack", StringComparison.OrdinalIgnoreCase) && !name.Equals("README.txt", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("This folder contains other files. Choose a dedicated MarineOps installation folder.");
        }
        foreach (string programName in new string[] { "MarineOps", "CargoTrack" })
        {
            string programDirectory = Path.Combine(target, programName);
            if (Directory.Exists(programDirectory)) ValidateProgramTree(programDirectory);
            else if (File.Exists(programDirectory))
                throw new ArgumentException("An installation program path is a file. Choose another folder.");
        }
    }

    private static void ValidateProgramTree(string directory)
    {
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new ArgumentException("Choose a regular installation folder without linked directories.");
        foreach (string entry in Directory.GetFileSystemEntries(directory))
        {
            FileAttributes attributes = File.GetAttributes(entry);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new ArgumentException("The installation contains linked files. Choose another folder.");
            if ((attributes & FileAttributes.Directory) != 0) { ValidateProgramTree(entry); continue; }
            string extension = Path.GetExtension(entry).ToLowerInvariant();
            bool database = extension == ".db" || extension == ".sqlite" || extension == ".sqlite3";
            if (!database)
            {
                using (FileStream stream = new FileStream(entry, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                {
                    byte[] header = new byte[16];
                    if (stream.Read(header, 0, header.Length) == header.Length)
                        database = System.Text.Encoding.ASCII.GetString(header) == "SQLite format 3\0";
                }
            }
            if (database)
                throw new ArgumentException("This installation folder contains a database. Move the database to a separate data folder in Settings before upgrading: " + entry);
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
        shortcutType.InvokeMember("Description", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { "MarineOps" });
        shortcutType.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { target+",0" });
        shortcutType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
        Marshal.FinalReleaseComObject(shortcut);
        string legacyLink = Path.Combine(desktop, "Cargo Track.lnk");
        if (name == "MarineOps" && File.Exists(legacyLink))
        {
            object oldShortcut = shellType.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { legacyLink });
            string oldTarget = (string)oldShortcut.GetType().InvokeMember("TargetPath", System.Reflection.BindingFlags.GetProperty, null, oldShortcut, null);
            string legacyTarget = Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(target)), "CargoTrack", "CargoTrack.exe");
            if (String.Equals(oldTarget, legacyTarget, StringComparison.OrdinalIgnoreCase)) File.Delete(legacyLink);
            Marshal.FinalReleaseComObject(oldShortcut);
        }
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
        Text = "MarineOps setup";
        Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Font = new Font("Segoe UI", 11);
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(620, 280);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        Label heading = new Label { Text = "Install MarineOps 1.2.6", AutoSize = true, Location = new Point(24, 20), Font = new Font(Font, FontStyle.Bold) };
        Label label = new Label { Text = "Installation folder", AutoSize = true, Location = new Point(24, 60) };
        PathInput.Text = initialPath; PathInput.SetBounds(24, 88, 450, 30); PathInput.AccessibleName = "Installation folder";
        Button browse = new Button { Text = "Browse…", Location = new Point(484, 86), Size = new Size(112, 34) };
        browse.Click += delegate {
            using (FolderBrowserDialog picker = new FolderBrowserDialog()) {
                picker.Description = "Choose a dedicated MarineOps installation folder";
                if (Directory.Exists(PathInput.Text)) picker.SelectedPath = PathInput.Text;
                if (picker.ShowDialog(this) == DialogResult.OK) PathInput.Text = picker.SelectedPath;
            }
        };
        ShortcutOption.Text = "Create desktop shortcut"; ShortcutOption.Checked = shortcut;
        ShortcutOption.SetBounds(24, 134, 420, 28);
        LaunchOption.Text = "Launch MarineOps after installation"; LaunchOption.Checked = launch;
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
