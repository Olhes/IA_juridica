param([switch]$Check)

$ErrorActionPreference = 'Stop'
$java = 'C:\Herramientas\jdk-21\bin\java.exe'
$launcher = 'D:\Installations\sonarqube-26.11.0.134175\bin\windows-x86-64\StartSonar.bat'

foreach ($file in @($java, $launcher)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        Write-Error "No se encontró el archivo requerido: $file"
    }
}

if ($Check) {
    Write-Output 'Java y el lanzador de SonarQube están disponibles.'
    exit 0
}

$env:SONAR_JAVA_PATH = $java
Write-Output 'Iniciando SonarQube. Mantén esta terminal abierta hasta que quieras detenerlo.'
& $launcher
exit $LASTEXITCODE
