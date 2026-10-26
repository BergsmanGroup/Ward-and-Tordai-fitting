param(
    [string]$Ref = ""
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install it from https://cli.github.com/ and run 'gh auth login'."
}

if ([string]::IsNullOrWhiteSpace($Ref)) {
    $Ref = (git branch --show-current).Trim()
}

if ([string]::IsNullOrWhiteSpace($Ref)) {
    throw "Could not determine the current Git branch. Pass -Ref explicitly."
}

$trackedWorkflow = @(git ls-files ".github/workflows/package.yml")
if ($trackedWorkflow.Count -eq 0) {
    throw @"
The packaging workflow is not committed to this repository yet.
Commit and push .github/workflows/package.yml, then run this script again.
For example:
  git add .github/workflows/package.yml package-all.ps1 package.py
  git commit -m "Add cross-platform packaging workflow"
  git push origin $Ref
"@
}

Write-Host "Starting Windows and macOS packaging for '$Ref'..."
gh workflow run package.yml --ref $Ref
if ($LASTEXITCODE -ne 0) {
    throw @"
GitHub could not dispatch package.yml for '$Ref'.
Verify that the workflow has been pushed to GitHub and that 'gh auth status' succeeds.
"@
}

Write-Host "Workflow started. View progress with:"
Write-Host "  gh run list --workflow package.yml"
