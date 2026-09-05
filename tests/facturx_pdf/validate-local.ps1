param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$ReportPath,
    [string]$VeraPdf
)
$ErrorActionPreference = 'Stop'
if (-not $VeraPdf) { $VeraPdf = (Get-Command verapdf.bat -ErrorAction Stop).Source }
$resolvedPdf = (Resolve-Path -LiteralPath $PdfPath).Path
if (Test-Path -LiteralPath $ReportPath) { throw 'Report exists: choose a new path.' }
$result = & $VeraPdf --format xml --flavour 3b $resolvedPdf
$validatorExit = $LASTEXITCODE
$result | Set-Content -LiteralPath $ReportPath -Encoding UTF8
# Read the report, never infer PASS from an exit code or an XMP declaration.
[xml]$document = Get-Content -LiteralPath $ReportPath -Raw
$reports = $document.SelectNodes("//*[local-name()='validationReport']")
if ($validatorExit -ne 0 -or $reports.Count -ne 1 -or $reports[0].GetAttribute('isCompliant') -ne 'true') {
    throw 'PDF/A-3b FAIL or non attestee; inspect the veraPDF XML report.'
}
Write-Output 'PDF/A-3b PASS (veraPDF)'
