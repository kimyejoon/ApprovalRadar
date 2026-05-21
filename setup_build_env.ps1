# ApprovalRadar Windows Build Environment Setup & Build Run Script

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   ApprovalRadar Build Setup Script" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Ensure destination directory for Node.js exists
$programsDir = Join-Path $env:USERPROFILE "Programs"
if (-not (Test-Path $programsDir)) {
    New-Item -ItemType Directory -Path $programsDir | Out-Null
    Write-Host "[INFO] Created directory: $programsDir" -ForegroundColor Green
}

# 1. Download & Install Python 3.11
$pythonPath = "python"
$pythonInstalled = $false
try {
    $ver = python --version 2>&1
    if ($ver -match "Python 3\.(11|12)") {
        Write-Host "[OK] Python is already installed: $ver" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {}

if (-not $pythonInstalled) {
    # Check if python is in user AppData already
    $userPythonDir = Join-Path $env:USERPROFILE "AppData\Local\Programs\Python"
    $localPythonExe = Get-ChildItem -Path $userPythonDir -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    
    if ($localPythonExe) {
        Write-Host "[OK] Found local Python installation at: $($localPythonExe.FullName)" -ForegroundColor Green
        $pythonInstalled = $true
        # Add to PATH for session
        $pythonBinDir = Split-Path $localPythonExe.FullName -Parent
        $pythonScriptsDir = Join-Path $pythonBinDir "Scripts"
        $env:Path = "$pythonBinDir;$pythonScriptsDir;" + $env:Path
    } else {
        $pythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $pythonInstaller = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
        
        Write-Host "[INFO] Downloading Python 3.11.9..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller
        
        Write-Host "[INFO] Installing Python silently (User-only, adds to path)..." -ForegroundColor Yellow
        $process = Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1" -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Write-Error "Python installation failed with exit code $($process.ExitCode)"
        }
        Write-Host "[OK] Python installation completed." -ForegroundColor Green
        
        # Refresh PATH from registry for the current process
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $env:Path = "$userPath;$machinePath"
    }
}

# 2. Download & Extract Node.js 22 (LTS) - required by Vite 8 / Rolldown
$nodeDir = Join-Path $programsDir "node-v22.12.0-win-x64"
if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
    $nodeUrl = "https://nodejs.org/dist/v22.12.0/node-v22.12.0-win-x64.zip"
    $nodeZip = Join-Path $env:TEMP "node-v22.12.0-win-x64.zip"
    
    Write-Host "[INFO] Downloading Node.js 22.12.0 LTS..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip
    
    Write-Host "[INFO] Extracting Node.js..." -ForegroundColor Yellow
    Expand-Archive -Path $nodeZip -DestinationPath $programsDir -Force
    Write-Host "[OK] Node.js extraction completed." -ForegroundColor Green
} else {
    Write-Host "[OK] Node.js is already present in $nodeDir" -ForegroundColor Green
}

# Add Node.js to current session path
$env:Path = "$nodeDir;" + $env:Path

# Verify paths and versions
Write-Host "`nChecking environment tool versions:" -ForegroundColor Cyan
try {
    $pyVer = python --version
    Write-Host "[VER] Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Error "Python execution failed. Please verify installation."
}

try {
    $nodeVer = node --version
    Write-Host "[VER] Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Error "Node.js execution failed."
}

try {
    $npmVer = npm --version
    Write-Host "[VER] npm: $npmVer" -ForegroundColor Green
} catch {
    Write-Error "npm execution failed."
}

# 3. Clean FE node_modules and package-lock.json to avoid rolldown native binding issues on Windows
$feDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) "ApprovalRadar-FE"
Write-Host "`n[INFO] Cleaning Frontend node_modules & package-lock.json to avoid Windows native binding errors..." -ForegroundColor Yellow
if (Test-Path (Join-Path $feDir "node_modules")) {
    Remove-Item -Recurse -Force (Join-Path $feDir "node_modules")
}
if (Test-Path (Join-Path $feDir "package-lock.json")) {
    Remove-Item -Force (Join-Path $feDir "package-lock.json")
}
Write-Host "[OK] Clean complete." -ForegroundColor Green

# 4. Execute Build Script
Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "   Running build.bat" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
cd $scriptDir

# Run build.bat using cmd.exe
cmd.exe /c build.bat
