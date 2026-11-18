# 제주 사장님 상권비서 — 설치 (Windows 10/11, Windows PowerShell 5.1 이상)
# install.bat을 더블클릭하면 이 파일이 실행됩니다.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "== 제주 사장님 상권비서 설치 ==" -ForegroundColor Cyan
Write-Host "설치 위치: $Root"

function Test-Py([string]$exe, [string[]]$pre) {
  try {
    $out = & $exe @pre -c "import sys;print(sys.executable if sys.version_info[:2]>=(3,11) else '')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return ($out | Select-Object -Last 1).Trim() }
  } catch {}
  return ""
}

function Find-Python {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("-3.11", "-3.12", "-3.13")) {
      $p = Test-Py "py" @($v)
      if ($p) { return $p }
    }
  }
  foreach ($exe in @("python", "python3")) {
    $cmd = Get-Command $exe -ErrorAction SilentlyContinue
    if ($cmd -and ($cmd.Source -notlike "*WindowsApps*")) {
      $p = Test-Py $exe @()
      if ($p) { return $p }
    }
  }
  return ""
}

# 1) Python 3.11 이상 찾기
$pyExe = Find-Python
if (-not $pyExe) {
  Write-Host "Python 3.11 이상을 찾지 못했습니다." -ForegroundColor Yellow
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    $a = Read-Host "winget으로 Python 3.11을 설치할까요? (Y/N)"
    if ($a -match "^[Yy]") {
      winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements
      $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
      $pyExe = Find-Python
    }
  }
  if (-not $pyExe) {
    Write-Host "https://www.python.org/downloads/windows/ 에서 Python 3.11을 설치한 뒤(설치 첫 화면의 'Add python.exe to PATH' 체크) install.bat을 다시 실행해 주세요." -ForegroundColor Red
    Start-Process "https://www.python.org/downloads/windows/"
    Read-Host "Enter를 누르면 닫힙니다"
    exit 1
  }
}
Write-Host "Python: $pyExe"

# 2) 가상환경(.venv) 만들기 — 이 폴더 안에만 설치되어 PC의 다른 프로그램에 영향을 주지 않습니다.
$vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
  Write-Host "가상환경을 만드는 중..."
  & $pyExe -m venv (Join-Path $Root ".venv")
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $vpy)) {
    Write-Host "가상환경을 만들지 못했습니다." -ForegroundColor Red
    Read-Host "Enter를 누르면 닫힙니다"; exit 1
  }
}

# 3) 패키지 설치 (requirements.txt에 버전을 고정해 두었습니다)
Write-Host "필요한 패키지를 설치하는 중... (인터넷 연결 필요, 3~10분)"
& $vpy -m pip install --upgrade pip --disable-pip-version-check
& $vpy -m pip install -r (Join-Path $Root "requirements.txt") --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
  Write-Host "패키지 설치에 실패했습니다. 인터넷 연결(또는 방화벽의 pypi.org 허용)을 확인한 뒤 다시 실행해 주세요." -ForegroundColor Red
  Read-Host "Enter를 누르면 닫힙니다"; exit 1
}

# 4) 설치 확인
& $vpy -c "import streamlit, pandas, matplotlib, docx, openpyxl; print('패키지 확인 완료')"
if ($LASTEXITCODE -ne 0) {
  Write-Host "패키지 확인에 실패했습니다." -ForegroundColor Red
  Read-Host "Enter를 누르면 닫힙니다"; exit 1
}
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data"), (Join-Path $Root "outputs") | Out-Null

# 5) 운영자 PIN — 운영자 설정(API 키·데이터 폴더)은 PIN을 아는 사람만 엽니다. PIN 원문은 저장하지 않습니다.
Push-Location $Root
# 센터 PC 설치면 실행 모드를 '센터'로 기록(체험 버튼을 접어 둠). 저장소 기본값은 '체험'.
$ans = Read-Host "센터 PC에 설치하나요? (Y = 센터 모드 / Enter = 체험 모드)"
if ($ans -match '^[Yy]') { & $vpy -c "from jeju_agent import llm; s = llm.load_settings(); s['app_mode'] = '\uc13c\ud130'; llm.save_settings(s)" }
& $vpy -m jeju_agent.admin status | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "운영자 PIN을 정해 주세요(숫자 6~12자리). 방문자는 운영자 설정을 볼 수 없게 됩니다." -ForegroundColor Cyan
  & $vpy -m jeju_agent.admin set-pin
}
Pop-Location

# 6) 바탕화면 바로가기
try {
  $desk = [Environment]::GetFolderPath("Desktop")
  $ws = New-Object -ComObject WScript.Shell
  $lnk = $ws.CreateShortcut((Join-Path $desk "제주 사장님 상권비서.lnk"))
  $lnk.TargetPath = (Join-Path $Root "run.bat")
  $lnk.WorkingDirectory = $Root
  $lnk.Description = "제주 사장님 상권비서 — 제주빅데이터센터 카드 데이터 상권분석"
  $lnk.Save()
  Write-Host "바탕화면에 '제주 사장님 상권비서' 바로가기를 만들었습니다."
} catch {
  Write-Host "바로가기를 만들지 못했습니다(실행은 run.bat으로 할 수 있습니다)."
}

Write-Host ""
Write-Host "설치가 끝났습니다. 바탕화면 바로가기 또는 run.bat으로 실행하세요." -ForegroundColor Green
Write-Host "AI 기능·지원사업 찾기·데이터허브 자동 받기용 키는 실행 후 '운영자 설정' 탭에서 넣을 수 있습니다(선택)."
Read-Host "Enter를 누르면 닫힙니다"
