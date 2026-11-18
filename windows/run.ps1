# 제주 사장님 상권비서 — 실행 (run.bat 또는 바탕화면 바로가기)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$vpy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
  Write-Host "아직 설치되지 않았습니다. install.bat을 먼저 실행해 주세요." -ForegroundColor Yellow
  Read-Host "Enter를 누르면 닫힙니다"; exit 1
}

# 비어 있는 포트 찾기(8501부터)
$port = 8501
while (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { $port++ }

# 서버가 준비되면 브라우저 열기(별도 작업)
Start-Job -ArgumentList $port -ScriptBlock {
  param($p)
  for ($i = 0; $i -lt 90; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$p/_stcore/health" -TimeoutSec 2
      if ($r.Content -match "ok") { Start-Process "http://localhost:$p"; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
} | Out-Null

Write-Host "== 제주 사장님 상권비서 ==" -ForegroundColor Cyan
Write-Host "잠시 후 브라우저가 열립니다. 열리지 않으면 주소창에 http://localhost:$port 를 입력하세요."
Write-Host "이 검은 창을 닫으면 프로그램이 종료됩니다. 퇴실 전에는 화면 왼쪽 '내 작업 모두 지우기'를 눌러 주세요."
& $vpy -m streamlit run (Join-Path $Root "app.py") --server.port $port --server.headless true --browser.gatherUsageStats false
