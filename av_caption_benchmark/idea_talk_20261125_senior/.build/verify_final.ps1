$ErrorActionPreference='Stop'
$final=Get-ChildItem -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'output') -Filter '*.pptx' | Select-Object -First 1
$render=Join-Path $PSScriptRoot 'renders_final'
[void](New-Item -ItemType Directory -Path $render -Force)
$app=New-Object -ComObject PowerPoint.Application
$deck=$app.Presentations.Open($final.FullName,-1,0,0)
$issues=@()
$cellCount=0
for($i=1;$i -le $deck.Slides.Count;$i++) {
  $slide=$deck.Slides.Item($i)
  foreach($shape in $slide.Shapes) {
    if($shape.HasTable -eq -1) {
      $table=$shape.Table
      for($r=1;$r -le $table.Rows.Count;$r++) {
        for($c=1;$c -le $table.Columns.Count;$c++) {
          $cell=$table.Cell($r,$c).Shape
          $cellCount++
          $available=$cell.Height-$cell.TextFrame.MarginTop-$cell.TextFrame.MarginBottom
          $actual=$cell.TextFrame.TextRange.BoundHeight
          if($actual -gt $available+1) {$issues += [pscustomobject]@{slide=$i;row=$r;column=$c;available=[double]$available;actual=[double]$actual}}
        }
      }
    }
  }
}
$deck.Export($render,'PNG',1600,900)
[pscustomobject]@{slides=$deck.Slides.Count;checkedTableCells=$cellCount;tableOverflow=$issues;nativePowerPointOpenAndRender=$true} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'native_verification.json') -Encoding UTF8
$deck.Close()
$app.Quit()
Write-Output ('Native open/render passed. Table cells: '+$cellCount+'; overflow findings: '+$issues.Count)
