param(
    [string]$Host = '127.0.0.1',
    [int]$Port = 8000,
    [string]$Server = 'daphne'
)

Write-Host "Starting ASGI server using $Server on $Host:$Port"

if ($Server -ieq 'daphne') {
    # Start Daphne
    daphne -b $Host -p $Port cloudvault.asgi:application
} elseif ($Server -ieq 'uvicorn') {
    uvicorn cloudvault.asgi:application --host $Host --port $Port --reload
} else {
    Write-Error "Unknown server '$Server'. Supported: daphne, uvicorn"
}
