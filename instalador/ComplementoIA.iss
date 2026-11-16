; Instalador del complemento de IA de ConverterSmartGrid (spec 086, RF-37, RF-39; auditoría de lanzamiento L8, 2026-11-14).
;
; Compilar, con el complemento ya armado por «tools/construir_candidato.py complemento-ia --modelos ...»:
;   ISCC.exe /DComplemento=C:\ruta\complemento instalador\ComplementoIA.iss
;
; En la misma línea que instalador\ConverterSmartGrid.iss: por usuario, sin internet ni pip a mano. Todo el trabajo lo
; hace «instalar_candidato.py complemento» con el Python del programa ya instalado: comprueba cada huella, instala las
; ruedas sin red en la versión que se usa y deja los modelos y Ollama en {app}\complemento_ia. Antes el manual pedía
; ejecutar pip a mano en una copia separada, y el operador no tenía cómo.
;
; La versión sale de version.txt del complemento, que la escribe el constructor con la del paquete (086:RF-92); el
; complemento solo se instala sobre el programa de esa misma versión.

#ifndef Complemento
  #error Falta /DComplemento=carpeta del complemento
#endif
#define FicheroVersion AddBackslash(Complemento) + "version.txt"
#if !FileExists(FicheroVersion)
  #error El complemento no trae version.txt
#endif
#define Lector FileOpen(FicheroVersion)
#define Version Trim(FileRead(Lector))
#expr FileClose(Lector)
#if Version == ""
  #error version.txt del complemento esta vacio
#endif
#pragma message "Version del complemento: " + Version

[Setup]
AppId={{2D6E5C1B-7A3F-4E0B-9C51-202611140086}
AppName=ConverterSmartGrid - complemento de IA
AppVersion={#Version}
; La carpeta es la del programa: la lee CarpetaDelPrograma del registro de su instalador.
DefaultDirName={code:CarpetaDelPrograma}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ConverterSmartGrid-complemento-ia-{#Version}-setup
OutputDir={#SourcePath}\salida
Compression=lzma2/normal
SolidCompression=no
; Los pesos pasan de 4 GB: Inno Setup los reparte en ficheros setup-*.bin junto al .exe.
DiskSpanning=yes
DiskSliceSize=max
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
UninstallDisplayName=ConverterSmartGrid - complemento de IA

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "{#Complemento}\*"; DestDir: "{app}\_complemento"; Flags: recursesubdirs createallsubdirs ignoreversion deleteafterinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}\complemento_ia"
Type: filesandordirs; Name: "{app}\complemento_ia.preparando"
Type: filesandordirs; Name: "{app}\complemento_ia.retirar"
Type: filesandordirs; Name: "{app}\_complemento"

[Code]
const
  ClavePrograma = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F0B1C52-8A3E-4C57-9B0E-6F4C2D7A1E86}_is1';
  FicheroMotivo = 'motivo_complemento.txt';

var
  FalloInstalacion: Boolean;

function CarpetaDelPrograma(Param: String): String;
begin
  { El programa se instala por usuario; su instalador deja aquí su carpeta. Sin él, la de siempre. }
  if not RegQueryStringValue(HKCU, ClavePrograma, 'InstallLocation', Result) then
    Result := ExpandConstant('{localappdata}\Programs\ConverterSmartGrid');
  Result := RemoveBackslash(Result);
end;

function LeerPuntero(const Fichero: String): String;
var
  Texto: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(Fichero, Texto) then
    Result := Trim(String(Texto));
end;

function InitializeSetup: Boolean;
var
  Actual: String;
begin
  { Sin el programa de la misma versión no hay Python con el que instalar: se dice antes de copiar 10 GB. }
  Actual := LeerPuntero(CarpetaDelPrograma('') + '\actual.txt');
  Result := Actual = '{#Version}';
  if not Result then
    SuppressibleMsgBox('Este complemento es de ConverterSmartGrid {#Version}. ' +
      'Instale antes el programa de esa version (ahora hay: ' + Actual + ').', mbError, MB_OK, IDOK);
end;

function MotivoDelFallo: String;
var
  Lineas: TArrayOfString;
  I: Integer;
begin
  Result := '';
  if LoadStringsFromFile(ExpandConstant('{tmp}\' + FicheroMotivo), Lineas) then
    for I := 0 to GetArrayLength(Lineas) - 1 do
      if Trim(Lineas[I]) <> '' then
        Result := Result + Trim(Lineas[I]) + #13#10;
end;

procedure InstalarComplemento;
var
  CodigoProceso: Integer;
  Python: String;
begin
  FalloInstalacion := True;
  Python := ExpandConstant('{app}\versiones\{#Version}\python\python.exe');
  WizardForm.StatusLabel.Caption := 'Comprobando las huellas e instalando el complemento...';
  if Exec(Python, ExpandConstant('"{app}\_complemento\instalador\instalar_candidato.py" complemento --complemento "{app}\_complemento" --destino "{app}"'
      + ' --registro "{tmp}\' + FicheroMotivo + '"'), '', SW_HIDE, ewWaitUntilTerminated, CodigoProceso) then
  begin
    Log(Format('Resultado de instalar_candidato.py complemento: %d', [CodigoProceso]));
    FalloInstalacion := (CodigoProceso <> 0) or not FileExists(ExpandConstant('{app}\complemento_ia\instalado.json'));
  end;
  if FalloInstalacion then
  begin
    Log('No se pudo instalar el complemento: ' + MotivoDelFallo);
    SuppressibleMsgBox('No se pudo instalar el complemento de IA. El programa sigue como estaba.' + #13#10#13#10 + MotivoDelFallo,
      mbError, MB_OK, IDOK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstalarComplemento;
end;

function GetCustomSetupExitCode: Integer;
begin
  if FalloInstalacion then
    Result := 1
  else
    Result := 0;
end;
