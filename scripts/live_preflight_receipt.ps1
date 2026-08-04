Set-StrictMode -Version Latest

function Get-LiveReceiptProperty {
    [CmdletBinding()]
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$DefaultValue = $null
    )

    if ($null -eq $InputObject) {
        return $DefaultValue
    }

    $Property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $Property -or $null -eq $Property.Value) {
        return $DefaultValue
    }

    return $Property.Value
}

function Convert-LivePreflightReceipt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object]$Receipt
    )

    $Warnings = @()
    $RawWarnings = Get-LiveReceiptProperty -InputObject $Receipt -Name 'warnings' -DefaultValue @()
    foreach ($RawWarning in @($RawWarnings)) {
        if ($null -eq $RawWarning) {
            continue
        }

        $Warnings += [pscustomobject]@{
            category = [string](Get-LiveReceiptProperty -InputObject $RawWarning -Name 'category' -DefaultValue 'UNKNOWN')
            check = [string](Get-LiveReceiptProperty -InputObject $RawWarning -Name 'check' -DefaultValue 'unknown-check')
            error = [string](Get-LiveReceiptProperty -InputObject $RawWarning -Name 'error' -DefaultValue 'No sanitized warning was reported.')
        }
    }

    return [pscustomobject]@{
        status = [string](Get-LiveReceiptProperty -InputObject $Receipt -Name 'status' -DefaultValue 'FAILED')
        tradier_live_status = [string](Get-LiveReceiptProperty -InputObject $Receipt -Name 'tradier_live_status' -DefaultValue 'NOT REPORTED')
        warnings = $Warnings
        category = [string](Get-LiveReceiptProperty -InputObject $Receipt -Name 'category' -DefaultValue 'UNKNOWN')
        failed_check = [string](Get-LiveReceiptProperty -InputObject $Receipt -Name 'failed_check' -DefaultValue 'unknown-check')
        error = [string](Get-LiveReceiptProperty -InputObject $Receipt -Name 'error' -DefaultValue 'No sanitized error was reported.')
    }
}
