using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;
using System.ComponentModel;

[assembly: AssemblyTitle("MarineOps Setup")]
[assembly: AssemblyProduct("MarineOps")]
[assembly: AssemblyVersion("1.2.21.0")]
[assembly: AssemblyFileVersion("1.2.21.0")]

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
                using (InstallOptions options = new InstallOptions(installDir, desktopDir, shortcutName, !noShortcut, !noLaunch))
                {
                    options.ShowDialog();
                    return options.Failed ? 1 : 0;
                }
            }
            string warning;
            string installedExe = Install(installDir, desktopDir, shortcutName, !noShortcut, delegate { }, out warning);
            if (!noLaunch)
            {
                try { Process.Start(new ProcessStartInfo(installedExe) { UseShellExecute = true }); }
                catch { return 2; } // Installed, but launch failed.
            }
            return warning.Length == 0 ? 0 : 2; // Installed with a warning.
        }
        catch (Exception ex)
        {
            if (Array.IndexOf(args, "--quiet") < 0) MessageBox.Show(ex.Message, "MarineOps setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    internal static string Install(string installDir, string desktopDir, string shortcutName, bool shortcut, Action<string, int> report, out string warning)
    {
            warning = "";
            report("Preparing installation", -1);
            string fullTarget = Path.GetFullPath(installDir);
            ValidateInstallTarget(fullTarget);
            string parent = Path.GetDirectoryName(fullTarget);
            Directory.CreateDirectory(parent);
            string stage = fullTarget + ".installing-" + Guid.NewGuid().ToString("N");
            Directory.CreateDirectory(stage);
            try
            {
                Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("CargoTrackPayload");
                if (payload == null) throw new InvalidDataException("The installer payload is missing.");
                using (Stream fs = payload)
                using (ZipArchive archive = new ZipArchive(fs, ZipArchiveMode.Read))
                {
                    int total = archive.Entries.Count, completed = 0;
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
                        completed++;
                        report("Installing files", total == 0 ? 0 : (int)(90L * completed / total));
                    }
                }
                report("Finishing installation", -1);
                string exe = Path.Combine(stage, "MarineOps", "MarineOps.exe");
                if (!File.Exists(exe)) throw new InvalidDataException("The package is incomplete: MarineOps.exe was not found.");
                string previous = fullTarget + ".previous-" + Guid.NewGuid().ToString("N");
                bool movedPrevious = false;
                try
                {
                    if (Directory.Exists(fullTarget)) { Directory.Move(fullTarget, previous); movedPrevious = true; }
                    Directory.Move(stage, fullTarget);
                    if (movedPrevious)
                    {
                        try { Directory.Delete(previous, true); }
                        catch (Exception ex) { warning = "The previous program files could not be removed from " + previous + ". " + ex.Message; }
                    }
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
            if (shortcut)
            {
                report("Creating desktop shortcut", -1);
                try { CreateShortcut(installedExe, desktopDir, shortcutName); }
                catch (Exception ex) { warning += (warning.Length > 0 ? Environment.NewLine : "") + "The desktop shortcut could not be created. Open MarineOps from " + installedExe + ". " + ex.Message; }
            }
            return installedExe;
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
    private readonly TextBox path = new TextBox();
    private readonly CheckBox shortcut = new CheckBox(), launch = new CheckBox();
    private readonly Button browse = new Button(), primary = new Button(), secondary = new Button();
    private readonly Label heading = new Label(), detail = new Label(), status = new Label(), folder = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly string desktopDir, shortcutName;
    private bool running, finished;
    private string installedExe, installWarning;
    internal bool Failed { get; private set; }
    private readonly Color ink = Color.FromArgb(26, 42, 58), muted = Color.FromArgb(82, 102, 119);
    private readonly Color accent = Color.FromArgb(0, 107, 142), paper = Color.FromArgb(248, 251, 252);

    internal InstallOptions(string initialPath, string desktop, string name, bool makeShortcut, bool launchAfter)
    {
        desktopDir = desktop; shortcutName = name;
        Text = "MarineOps setup";
        Icon = Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);
        Font = new Font("Segoe UI", 10F); AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(760, 440); FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        BackColor = paper; ForeColor = ink;
        Panel brand = new Panel { BackColor = Color.FromArgb(16, 44, 65), Dock = DockStyle.Left, Width = 220 };
        PictureBox logo = new PictureBox { Image = Icon.ToBitmap(), SizeMode = PictureBoxSizeMode.Zoom, Location = new Point(28, 32), Size = new Size(52, 52) };
        Label wordmark = new Label { Text = "MarineOps", ForeColor = Color.White, AutoSize = true, Location = new Point(28, 102), Font = new Font("Segoe UI", 19F, FontStyle.Bold) };
        Label brandText = new Label { Text = "Cargo, personnel and\nvoyage operations", ForeColor = Color.FromArgb(197, 221, 229), Location = new Point(30, 152), Size = new Size(175, 58) };
        Label version = new Label { Text = "VERSION " + Assembly.GetExecutingAssembly().GetName().Version.ToString(3), ForeColor = Color.FromArgb(169, 206, 217), AutoSize = true, Location = new Point(30, 384), Font = new Font("Segoe UI", 9F) };
        brand.Controls.AddRange(new Control[] { logo, wordmark, brandText, version }); Controls.Add(brand);
        bool update = File.Exists(Path.Combine(initialPath, "MarineOps", "MarineOps.exe")) || File.Exists(Path.Combine(initialPath, "CargoTrack", "CargoTrack.exe"));
        heading.Text = update ? "Update MarineOps" : "Install MarineOps"; heading.Font = new Font("Segoe UI", 19F, FontStyle.Bold); heading.SetBounds(254, 28, 470, 42);
        detail.Text = update ? "Your existing Cargo and Personnel data will be kept." : "Choose where MarineOps will be installed for this Windows user.";
        detail.ForeColor = muted; detail.SetBounds(256, 78, 460, 46);
        folder.Text = "Installation folder"; folder.Font = new Font(Font, FontStyle.Bold); folder.SetBounds(256, 135, 450, 24);
        path.Text = initialPath; path.SetBounds(256, 164, 350, 28); path.AccessibleName = "Installation folder";
        browse.Text = "Browse…"; browse.SetBounds(614, 161, 112, 33);
        browse.Click += delegate {
            using (FolderBrowserDialog picker = new FolderBrowserDialog()) {
                picker.Description = "Choose a dedicated MarineOps installation folder";
                if (Directory.Exists(path.Text)) picker.SelectedPath = path.Text;
                if (picker.ShowDialog(this) == DialogResult.OK) path.Text = picker.SelectedPath;
            }
        };
        shortcut.Text = "Create desktop shortcut"; shortcut.Checked = makeShortcut; shortcut.SetBounds(256, 216, 440, 28);
        launch.Text = "Open MarineOps when I finish setup"; launch.Checked = launchAfter; launch.SetBounds(256, 253, 440, 28);
        status.ForeColor = muted; status.SetBounds(256, 150, 460, 120); status.Visible = false;
        progress.SetBounds(256, 283, 460, 18); progress.AccessibleName = "Installation progress"; progress.Visible = false;
        StyleButton(primary, true); StyleButton(secondary, false);
        primary.Text = update ? "Update" : "Install"; primary.SetBounds(498, 370, 108, 38);
        secondary.Text = "Cancel"; secondary.SetBounds(614, 370, 112, 38);
        primary.Click += PrimaryClick; secondary.Click += delegate { if (!running) Close(); };
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (running) e.Cancel = true; };
        Controls.AddRange(new Control[] { heading, detail, folder, path, browse, shortcut, launch, status, progress, primary, secondary });
        AcceptButton = primary; CancelButton = secondary; ActiveControl = primary;
    }
    private void StyleButton(Button button, bool emphasis)
    {
        button.FlatStyle = FlatStyle.Flat; button.FlatAppearance.BorderSize = emphasis ? 0 : 1;
        button.FlatAppearance.BorderColor = Color.FromArgb(180, 195, 204);
        button.BackColor = emphasis ? accent : paper; button.ForeColor = emphasis ? Color.White : ink; button.UseVisualStyleBackColor = false;
    }
    private void PrimaryClick(object sender, EventArgs e)
    {
        if (finished)
        {
            if (launch.Checked && !String.IsNullOrEmpty(installedExe))
            {
                try { Process.Start(new ProcessStartInfo(installedExe) { UseShellExecute = true }); }
                catch (Exception ex) { detail.Text = "MarineOps is installed, but could not be opened."; status.Text = "Open it manually from:\n" + installedExe + "\n\n" + ex.Message; launch.Checked = false; primary.Text = "Finish"; return; }
            }
            Close(); return;
        }
        string target;
        try { target = Path.GetFullPath(path.Text.Trim()); Installer.ValidateInstallTarget(target); }
        catch (Exception ex) { detail.Text = ex.Message; detail.ForeColor = Color.FromArgb(164, 38, 44); return; }
        bool createShortcut = shortcut.Checked;
        running = true; Failed = false; heading.Text = "Installing MarineOps";
        detail.Text = "Please keep this window open while setup completes."; detail.ForeColor = muted;
        folder.Visible = path.Visible = browse.Visible = shortcut.Visible = launch.Visible = false;
        status.Visible = progress.Visible = true; status.Text = "Preparing installation…"; progress.Style = ProgressBarStyle.Marquee;
        primary.Enabled = secondary.Enabled = false;
        BackgroundWorker worker = new BackgroundWorker(); worker.WorkerReportsProgress = true;
        worker.DoWork += delegate(object o, DoWorkEventArgs args) {
            string warning;
            string exe = Installer.Install(target, desktopDir, shortcutName, createShortcut,
                delegate(string stage, int value) { worker.ReportProgress(value < 0 ? 0 : value, new object[] { stage, value }); }, out warning);
            args.Result = new string[] { exe, warning };
        };
        worker.ProgressChanged += delegate(object o, ProgressChangedEventArgs args) {
            object[] update = (object[])args.UserState; status.Text = (string)update[0] + "…";
            int value = (int)update[1];
            if (value < 0) progress.Style = ProgressBarStyle.Marquee;
            else { if (progress.Style != ProgressBarStyle.Continuous) progress.Style = ProgressBarStyle.Continuous; progress.Value = Math.Min(90, Math.Max(0, value)); }
        };
        worker.RunWorkerCompleted += delegate(object o, RunWorkerCompletedEventArgs args) {
            running = false;
            if (args.Error != null) { ShowFailure(args.Error.Message); return; }
            string[] result = (string[])args.Result; installedExe = result[0]; installWarning = result[1]; finished = true; heading.Text = "MarineOps is ready"; detail.Text = installWarning.Length == 0 ? "Installation completed successfully." : "Installation completed with a warning.";
            status.Text = "Installed in:\n" + target + (installWarning.Length == 0 ? "" : "\n\n" + installWarning); progress.Visible = false;
            primary.Text = launch.Checked ? "Open MarineOps" : "Finish"; primary.SetBounds(478, 370, 128, 38);
            primary.Enabled = secondary.Enabled = true; secondary.Text = "Close";
        };
        worker.RunWorkerAsync();
    }
    private void ShowFailure(string message)
    {
        Failed = true; heading.Text = "Setup needs attention"; detail.Text = "Check the details below, then close setup and try again."; detail.ForeColor = muted;
        status.Text = message; status.ForeColor = Color.FromArgb(164, 38, 44); progress.Visible = false; primary.Visible = false; secondary.Enabled = true; secondary.Text = "Close";
    }
}
