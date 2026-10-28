$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$output=Join-Path $taskRoot 'output/audit-fixes-1.2.3'
$excel=$null;$book=$null;$report=@()
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false;$excel.DisplayAlerts=$false;$excel.AutomationSecurity=3
    foreach ($name in @('normal','long')) {
        $path=Join-Path $output ($name+'-plan.xlsx');$before=(Get-FileHash -LiteralPath $path).Hash
        $book=$excel.Workbooks.Open($path,0,$true)
        foreach ($item in @(@{sheet=1;name='berthing'},@{sheet=2;name='details'},@{sheet=3;name='transfer-print'})) {
            $s=$book.Worksheets.Item($item.sheet)
            if ($s.PageSetup.Zoom -ne 100 -or $s.PageSetup.PaperSize -ne 9) {throw 'Unexpected print scale / paper'}
            $s.ExportAsFixedFormat(0,(Join-Path $output ($name+'-'+$item.name+'.pdf')))
            $report+=@{name=($name+'-'+$item.name);sheet=$s.Name;paper_size=$s.PageSetup.PaperSize;
                orientation=$s.PageSetup.Orientation;zoom=$s.PageSetup.Zoom;rows=$s.UsedRange.Rows.Count;
                print_width_points=$s.Range($s.PageSetup.PrintArea).Width;repeat_titles=$s.PageSetup.PrintTitleRows}
        }
        $book.Close($false);$book=$null
        if ((Get-FileHash -LiteralPath $path).Hash -ne $before) {throw 'Validation changed workbook'}
    }
    foreach ($name in @('cargo-normal','cargo-long')) {
        $path=Join-Path $output ($name+'.xlsx');$before=(Get-FileHash -LiteralPath $path).Hash
        $book=$excel.Workbooks.Open($path,0,$true);$s=$book.ActiveSheet
        $s.ExportAsFixedFormat(0,(Join-Path $output ($name+'.pdf')))
        $report+=@{name=$name;sheet=$s.Name;paper_size=$s.PageSetup.PaperSize;orientation=$s.PageSetup.Orientation;
            zoom=$s.PageSetup.Zoom;rows=$s.UsedRange.Rows.Count;print_width_points=$s.Range($s.PageSetup.PrintArea).Width;
            repeat_titles=$s.PageSetup.PrintTitleRows}
        $book.Close($false);$book=$null
        if ((Get-FileHash -LiteralPath $path).Hash -ne $before) {throw 'Validation changed workbook'}
    }
    @{result='PASS';excel_version=$excel.Version;printer=$excel.ActivePrinter;source_workbooks_unchanged=$true;outputs=$report} |
        ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $output 'excel-native-checks.json')
    $report | ConvertTo-Json -Depth 5
} finally {
    if ($book) {$book.Close($false)}
    if ($excel) {$excel.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)}
}
