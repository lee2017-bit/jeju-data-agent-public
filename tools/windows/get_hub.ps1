# 제주데이터허브 '관광지 및 상업지구' 카드 데이터 등 6종을 한 번에 CSV로 받기(PC용)
# 왜 PC에서? 제주데이터허브(open.jejudatahub.net)는 클라우드·해외 IP를 웹방화벽으로 막아, 개발 환경에서는 받을 수 없습니다.
# 실행: 제주데이터허브에 로그인해 아래 6종을 프로젝트에 담고, 프로젝트키를 복사(Ctrl+C)한 뒤 get_hub.bat 더블클릭.
#       설치 필요 없음(Windows 기본 PowerShell). 키는 파일에 저장하지 않습니다.
param(
  [string]$AppKey = "",
  [string]$Start = "201601",
  [string]$End = "202112"
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 공공데이터포털 참고문서(2020.12판)에 적힌 데이터허브 API 주소. 2026-11-04 실행에서 6개 모두 404 → 바뀐 것으로 보임.
# 실패하면 데이터허브 상세 페이지의 API 요청 주소를 복사해 넣으라고 묻는다.
$Sets = @(
  @{ Name = "요일별";       Title = "관광지 및 상업지구 요일별 카드 데이터";        Api = "868ttD1tbDb8tbt00tDtaba6t0Db1110" },
  @{ Name = "시간대별";     Title = "관광지 및 상업지구 시간대별 카드 데이터";      Api = "DD7a1ta6tba70bt7tD1D1aDttDt701b7" },
  @{ Name = "업종별";       Title = "관광지 및 상업지구 업종별 카드 데이터";        Api = "a0b10aat1ata50aat5tbb1at011D1060" },
  @{ Name = "이용자유형별"; Title = "관광지 및 상업지구 이용자 유형별 카드 데이터"; Api = "61aa1D6t1ab44taD1bDb10Dt1Dt41tDD" },
  @{ Name = "연령성별";     Title = "관광지 및 상업지구 연령대, 성별 카드 데이터";   Api = "6tt1tt0a6a01t616t6a0abb6606ta606" },
  @{ Name = "테마별";       Title = "내국인 관광객 테마별 카드 이용 데이터";         Api = "t5519aD915tt999tbbatab5b1tb5b9ta" }
)

if (-not $AppKey) {
  $clip = ""
  try { $clip = (Get-Clipboard -Format Text | Out-String).Trim() } catch {}
  if ($clip -and ($clip -notmatch "\s") -and $clip.Length -ge 8 -and $clip.Length -le 200) {
    $shown = $clip.Substring(0, [Math]::Min(4, $clip.Length)) + "..." + " (" + $clip.Length + "자)"
    $a = Read-Host "클립보드에 복사된 키를 쓸까요? $shown  [Enter=예 / N=직접 입력]"
    if ($a -notmatch "^[Nn]") { $AppKey = $clip }
  }
  if (-not $AppKey) {
    Write-Host "프로젝트키를 붙여 넣고 Enter를 누르세요. (붙여넣기: 창 안에서 마우스 오른쪽 버튼 한 번)"
    $AppKey = Read-Host "프로젝트키"
  }
}
$AppKey = $AppKey.Trim()
$OutDir = Join-Path $PSScriptRoot ("허브_카드6종_" + (Get-Date -Format "yyyyMMdd"))
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ok = @(); $fail = @()

function Get-Rows([string]$Api) {
  $rows = New-Object System.Collections.ArrayList
  $n = 1
  do {
    $url = "https://open.jejudatahub.net/api/proxy/$Api/${AppKey}?startDate=$Start&endDate=$End&number=$n&limit=100"
    $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 60
    if ($r.data) { [void]$rows.AddRange(@($r.data)) }
    Write-Host ("  받는 중: {0} / {1}" -f $rows.Count, $r.totCnt)
    $n++
    Start-Sleep -Milliseconds 200
  } while ($r.hasMore -and $r.data)
  return ,$rows
}

function Read-ApiId([string]$Title) {
  # 데이터허브 데이터 상세 페이지의 API 요청 주소(…/api/proxy/아이디/…)를 클립보드나 입력에서 읽는다
  Write-Host ""
  Write-Host "  데이터허브에서 '$Title' 상세 페이지를 열고," -ForegroundColor Yellow
  Write-Host "  API 요청 주소(https://open.jejudatahub.net/api/proxy/... 로 시작)를 복사(Ctrl+C)한 뒤 여기서 Enter를 누르세요." -ForegroundColor Yellow
  Write-Host "  (건너뛰려면 S 입력 후 Enter)"
  for ($t = 0; $t -lt 3; $t++) {
    $a = Read-Host "  준비되면 Enter"
    if ($a -match "^[Ss]$") { return "" }
    $text = $a
    if (-not ($text -match "api/proxy/")) {
      try { $text = (Get-Clipboard -Format Text | Out-String) } catch { $text = "" }
    }
    if ($text -match "api/proxy/([A-Za-z0-9]+)") { return $Matches[1] }
    Write-Host "  주소에서 'api/proxy/아이디'를 찾지 못했습니다. 다시 복사한 뒤 Enter를 누르거나, 주소를 직접 붙여 넣으세요." -ForegroundColor Red
  }
  return ""
}

$found = @()
foreach ($s in $Sets) {
  Write-Host ""
  Write-Host ("[{0}] {1}" -f $s.Name, $s.Title) -ForegroundColor Cyan
  $rows = $null; $err = ""
  try { $rows = Get-Rows $s.Api } catch { $err = $_.Exception.Message }
  if ($err -or -not $rows -or $rows.Count -eq 0) {
    if (-not $err) { $err = "받은 행이 0개" }
    Write-Host "  기본 주소로 실패: $err" -ForegroundColor Red
    $id = Read-ApiId $s.Title
    if ($id) {
      $err = ""
      try { $rows = Get-Rows $id; $s.Api = $id } catch { $err = $_.Exception.Message }
    }
  }
  if ($err -or -not $rows -or $rows.Count -eq 0) {
    if (-not $err) { $err = "받은 행이 0개" }
    Write-Host "  실패: $err" -ForegroundColor Red
    $fail += $s.Name
    continue
  }
  $found += ("{0}`t{1}`t{2}" -f $s.Name, $s.Title, $s.Api)
  $out = Join-Path $OutDir ("허브_{0}_카드_{1}-{2}.csv" -f $s.Name, $Start, $End)
  $rows | Export-Csv -Path $out -NoTypeInformation -Encoding UTF8
  Write-Host ("  완료: {0}행 → {1}" -f $rows.Count, (Split-Path $out -Leaf)) -ForegroundColor Green
  $ok += $s.Name
}

$zip = "$OutDir.zip"
if ($ok.Count -gt 0) {
  # 쓴 API 주소(아이디)도 함께 남긴다 — 키는 넣지 않는다
  $found | Out-File -FilePath (Join-Path $OutDir "api_ids.txt") -Encoding UTF8
  if (Test-Path $zip) { Remove-Item $zip -Force }
  Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $zip
}
Write-Host ""
Write-Host ("받음: {0}개 ({1})" -f $ok.Count, ($ok -join ", ")) -ForegroundColor Green
if ($fail.Count -gt 0) { Write-Host ("못 받음: {0}" -f ($fail -join ", ")) -ForegroundColor Red }
if ($ok.Count -gt 0) {
  Write-Host ""
  Write-Host "이 파일 하나를 채팅에 첨부해 주세요: $zip" -ForegroundColor Green
  Write-Host "(프로젝트키는 파일에 들어 있지 않습니다)"
}
Read-Host "Enter를 누르면 닫힙니다"
