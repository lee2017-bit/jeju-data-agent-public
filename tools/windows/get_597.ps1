# 제주데이터허브 597(내국인 관광객 지역·업종·성별·연령대별 카드 이용) 전체를 CSV로 받기
# 실행: 제주데이터허브에서 프로젝트키를 복사(Ctrl+C)한 뒤, 같은 폴더의 get_597.bat 더블클릭
#       (설치 필요 없음, Windows 기본 PowerShell 사용). 키는 파일에 저장하지 않습니다.
param(
  [string]$AppKey = "",
  [string]$Start = "201601",
  [string]$End = "202112"
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not $AppKey) {
  # 1) 클립보드에 복사해 둔 키를 먼저 확인(붙여넣기 문제를 피하기 위해)
  $clip = ""
  try { $clip = (Get-Clipboard -Format Text | Out-String).Trim() } catch {}
  if ($clip -and ($clip -notmatch "\s") -and $clip.Length -ge 8 -and $clip.Length -le 200) {
    $shown = $clip.Substring(0, [Math]::Min(4, $clip.Length)) + "..." + " (" + $clip.Length + "자)"
    $a = Read-Host "클립보드에 복사된 키를 쓸까요? $shown  [Enter=예 / N=직접 입력]"
    if ($a -notmatch "^[Nn]") { $AppKey = $clip }
  }
  # 2) 없으면 직접 입력(화면에 보입니다). 붙여넣기는 창 안에서 마우스 오른쪽 클릭.
  if (-not $AppKey) {
    Write-Host "프로젝트키를 붙여 넣고 Enter를 누르세요. (붙여넣기: 창 안에서 마우스 오른쪽 버튼 한 번)"
    Write-Host "※ 창 제목에 '선택'이 보이면 Esc를 눌러 주세요."
    $AppKey = Read-Host "프로젝트키"
  }
}
$AppKey = $AppKey.Trim()
$api = "5D5a577taba7tbb71at1b1bt9tatata9"
$rows = New-Object System.Collections.ArrayList
$n = 1
do {
  $url = "https://open.jejudatahub.net/api/proxy/$api/${AppKey}?startDate=$Start&endDate=$End&number=$n&limit=100"
  try {
    $r = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 60
  } catch {
    Write-Host "요청 실패(페이지 $n): $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "프로젝트키, 597 데이터를 프로젝트에 담았는지, 인터넷 연결을 확인해 주세요."
    Read-Host "Enter를 누르면 닫힙니다"; exit 1
  }
  if ($r.data) { [void]$rows.AddRange(@($r.data)) }
  Write-Host ("받는 중: {0} / {1}" -f $rows.Count, $r.totCnt)
  $n++
  Start-Sleep -Milliseconds 200
} while ($r.hasMore -and $r.data)
$out = Join-Path $PSScriptRoot ("허브597_내국인관광객_카드이용_{0}-{1}.csv" -f $Start, $End)
$rows | Select-Object sido, sigungu, cityGubun, marketType, userType, ageGroup, gender, dtYearMonth, userCount, useCount, useCost |
  Export-Csv -Path $out -NoTypeInformation -Encoding UTF8
Write-Host ""
Write-Host "완료: $($rows.Count)행 → $out" -ForegroundColor Green
Write-Host "이 CSV 파일을 채팅에 첨부해 주세요. (프로젝트키는 파일에 들어 있지 않습니다)"
Read-Host "Enter를 누르면 닫힙니다"
