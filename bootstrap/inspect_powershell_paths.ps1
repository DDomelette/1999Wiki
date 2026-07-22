param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path -LiteralPath $Path).Path,
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_.Message }
    exit 2
}

$nodes = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
        $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]
}, $true)

$result = @($nodes | ForEach-Object {
    [ordered]@{
        line = $_.Extent.StartLineNumber
        column = $_.Extent.StartColumnNumber
        value = $_.Value
    }
})
ConvertTo-Json -InputObject $result -Compress
