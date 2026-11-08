; Instalador de ConverterSmartGrid (spec 086, RF-36, RF-38, RF-39). Probado en una compilación real: compilado el 2026-11-04 (086 T40).
;
; Compilar, con el candidato ya armado por tools/construir_candidato.py:
;   ISCC.exe /DCandidato=C:\ruta\candidato /DVersion=1.0.0rc1 instalador\ConverterSmartGrid.iss
;
; No sale a internet, ni pide Node ni pytest. Todo el trabajo lo hace instalar_candidato.py con el Python del propio
; paquete: comprueba cada huella, instala con pip sin red y solo cambia de versión si la nueva responde al doctor.
; Por usuario y sin administrador: el puesto es de un operador (D2), y los datos quedan en su carpeta, no aquí.

#ifndef Candidato
  #error Falta /DCandidato=carpeta del candidato
#endif
#ifndef Version
  #error Falta /DVersion=version del manifiesto del candidato
#endif

[Setup]
AppId={{6F0B1C52-8A3E-4C57-9B0E-6F4C2D7A1E86}
AppName=ConverterSmartGrid
AppVersion={#Version}
DefaultDirName={localappdata}\Programs\ConverterSmartGrid
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ConverterSmartGrid-{#Version}-setup
OutputDir={#SourcePath}\salida
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Actualizar deja la versión anterior instalada para poder volver: no se cierra nada por sorpresa.
CloseApplications=no
UninstallDisplayName=ConverterSmartGrid

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"

[Files]
; El candidato se deja en una carpeta temporal del programa, y se borra al terminar.
Source: "{#Candidato}\*"; DestDir: "{app}\_entrega"; Flags: recursesubdirs createallsubdirs ignoreversion deleteafterinstall

[Icons]
Name: "{autoprograms}\ConverterSmartGrid"; Filename: "{app}\ConverterSmartGrid.cmd"
Name: "{autodesktop}\ConverterSmartGrid"; Filename: "{app}\ConverterSmartGrid.cmd"; Tasks: escritorio
Name: "{autoprograms}\ConverterSmartGrid - diagnostico"; Filename: "{cmd}"; Parameters: "/k ""{app}\csg.cmd"" doctor"

[UninstallDelete]
; Solo el programa. La carpeta de datos (%LOCALAPPDATA%\ConverterSmartGrid\datos) es del operador y se queda.
Type: filesandordirs; Name: "{app}\versiones"
Type: filesandordirs; Name: "{app}\_entrega"
Type: files; Name: "{app}\actual.txt"
Type: files; Name: "{app}\anterior.txt"
Type: files; Name: "{app}\ultima_copia.json"
Type: files; Name: "{app}\ConverterSmartGrid.cmd"
Type: files; Name: "{app}\csg.cmd"
Type: files; Name: "{app}\volver_atras.cmd"
Type: files; Name: "{app}\copia_datos.cmd"

[Code]
var
  FalloInstalacion: Boolean;

procedure ComprobarInstalacion;
var
  CodigoProceso: Integer;
  VersionActiva: AnsiString;
begin
  { RF-39: una carpeta anterior no salva un proceso fallido. El guion Python
    conserva el puntero anterior si falla; el contenedor debe devolver error. }
  FalloInstalacion := True;
  CodigoProceso := -1;
  WizardForm.StatusLabel.Caption := 'Comprobando las huellas e instalando...';
  if Exec(ExpandConstant('{app}\_entrega\terceros\python\python.exe'),
      ExpandConstant('"{app}\_entrega\instalador\instalar_candidato.py" instalar --candidato "{app}\_entrega" --destino "{app}"'),
      '', SW_HIDE, ewWaitUntilTerminated, CodigoProceso) then
  begin
    Log(Format('Resultado de instalar_candidato.py: %d', [CodigoProceso]));
    if (CodigoProceso = 0) and
        FileExists(ExpandConstant('{app}\versiones\{#Version}\python\python.exe')) and
        LoadStringFromFile(ExpandConstant('{app}\actual.txt'), VersionActiva) then
      FalloInstalacion := Trim(String(VersionActiva)) <> '{#Version}';
  end
  else
    Log(Format('No se pudo iniciar instalar_candidato.py: %d', [CodigoProceso]));
  if FalloInstalacion then
  begin
    Log('No se pudo terminar la instalacion. Se conserva el programa anterior.');
    if not WizardSilent then
      MsgBox('No se pudo terminar la instalacion. Lo que hubiera instalado sigue igual.', mbError, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    ComprobarInstalacion;
end;

function GetCustomSetupExitCode: Integer;
begin
  if FalloInstalacion then
    Result := 1
  else
    Result := 0;
end;
