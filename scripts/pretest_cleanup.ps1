# Remove Windows .lnk artifacts and __pycache__ everywhere

Get-ChildItem -Path . -Filter *.lnk -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -Force -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue