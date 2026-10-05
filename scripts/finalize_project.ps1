param([switch]$SkipHint)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$originalLocation = Get-Location
$oldPackage = $env:LAB_SOLUTION_PACKAGE
$oldTrace = $env:GRAPH_TRACE_DIR
$oldPythonEncoding = $env:PYTHONIOENCODING
$oldOutputEncoding = $OutputEncoding
$oldConsoleEncoding = [Console]::OutputEncoding

function Invoke-PythonStep {
    param([string[]]$PythonArguments, [string]$Log)
    & python @PythonArguments 2>&1 | Tee-Object -FilePath $Log
    if ($LASTEXITCODE -ne 0) { throw "Python step failed: $($PythonArguments -join ' ')" }
}

try {
    Set-Location -LiteralPath $projectRoot
    $env:PYTHONIOENCODING = 'utf-8'
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    New-Item -ItemType Directory -Force -Path 'report/evidence' | Out-Null
    Invoke-PythonStep -PythonArguments @('-m','pytest','tests','verification','-q','-p','no:cacheprovider') -Log 'report/evidence/tests.txt'
    # Both endpoints must work before any reset in the official benchmark.
    Invoke-PythonStep -PythonArguments @('-m','scripts.preflight_benchmark') -Log 'report/evidence/preflight.txt'
    if (-not $SkipHint) {
        $env:LAB_SOLUTION_PACKAGE = 'experiments.hint_solution'
        Invoke-PythonStep -PythonArguments @('bench_kg.py','--judge','--out','ket_qua_benchmark_kg.hint.txt') -Log 'report/evidence/benchmark_hint.txt'
    }
    $env:LAB_SOLUTION_PACKAGE = 'src'
    Invoke-PythonStep -PythonArguments @('bench_kg.py','--check') -Log 'report/evidence/check.txt'
    $env:GRAPH_TRACE_DIR = 'report/evidence/traces'
    # Last build is the final custom ontology, not the small --check graph.
    Invoke-PythonStep -PythonArguments @('bench_kg.py','--judge') -Log 'report/evidence/benchmark_final.txt'
    Invoke-PythonStep -PythonArguments @('-m','verification.check_live_graph') -Log 'report/evidence/live_checks.txt'
    Invoke-PythonStep -PythonArguments @('-m','scripts.update_benchmark_report') -Log 'report/evidence/report_update.txt'
    Write-Output 'Benchmark and report completed. Capture the three screenshots using report/NEO4J_QUERIES.cypher.'
}
finally {
    $env:LAB_SOLUTION_PACKAGE = $oldPackage
    $env:GRAPH_TRACE_DIR = $oldTrace
    $env:PYTHONIOENCODING = $oldPythonEncoding
    $OutputEncoding = $oldOutputEncoding
    [Console]::OutputEncoding = $oldConsoleEncoding
    Set-Location -LiteralPath $originalLocation.Path
}
