param([string]$WorkbookPath,[string]$ReportPrefix='',[string]$OutputDirectory='artifacts\personnel-development')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$output=Join-Path $taskRoot $OutputDirectory
New-Item -ItemType Directory -Force $output | Out-Null
if (!$WorkbookPath) { $WorkbookPath=Join-Path $output '20261006_Fleet Personnel Transfer Plan.xlsx' }
$before=(Get-FileHash -LiteralPath $WorkbookPath).Hash
$excel=$null
$book=$null
try {
    $excel=New-Object -ComObject Excel.Application
    $excel.Visible=$false
    $excel.DisplayAlerts=$false
    $excel.AutomationSecurity=3
    $book=$excel.Workbooks.Open($WorkbookPath,0,$true)
    if ($book.Worksheets.Count -notin @(2,3)) { throw 'Unexpected sheet count' }
    if ($book.Worksheets.Item(1).Name -ne 'Berthing Plan' -or $book.Worksheets.Item(2).Name -ne 'Transfer Details') { throw 'Unexpected sheet names' }
    $main=$book.Worksheets.Item(1)
    $main.ExportAsFixedFormat(0,(Join-Path $output ($ReportPrefix+'berthing-excel-print.pdf')))
    $details=$book.Worksheets.Item(2)
    $details.ExportAsFixedFormat(0,(Join-Path $output ($ReportPrefix+'transfer-details-excel-print.pdf')))
    $sheetNames=@($main.Name,$details.Name)
    if ($book.Worksheets.Count -eq 3) {
        $printable=$book.Worksheets.Item(3)
        if ($printable.Name -ne 'Transfer Print') { throw 'Unexpected print sheet' }
        $printable.ExportAsFixedFormat(0,(Join-Path $output ($ReportPrefix+'transfer-print-excel.pdf')))
        $sheetNames+=@($printable.Name)
    }
    $report=[ordered]@{excel_version=$excel.Version;printer=$excel.ActivePrinter;paper_size=$main.PageSetup.PaperSize;orientation=$main.PageSetup.Orientation;column_c_width=$main.Columns.Item(3).ColumnWidth;readonly_open='PASS';sheet_names=$sheetNames;main_rows=$main.UsedRange.Rows.Count;detail_rows=$details.UsedRange.Rows.Count;native_pdf_export='PASS';source_unchanged=$true}
    $book.Close($false)
    $book=$null
    if ((Get-FileHash -LiteralPath $WorkbookPath).Hash -ne $before) { throw 'Validation changed workbook bytes' }
    $report | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $output ($ReportPrefix+'excel-native-validation.json'))
    $report | ConvertTo-Json
} finally {
    if ($book) { $book.Close($false) }
    if ($excel) { $excel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) }
}
