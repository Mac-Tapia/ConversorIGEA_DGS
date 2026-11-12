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

; /DEnsayoQA conserva la instalación de producto, incluidos sus accesos.
; La receta de QA fija también /DIR y CSG_DATOS_HOME al espacio de ensayo.
#ifdef EnsayoQA
#define IdentidadApp "{{A377620D-88D7-4C7E-8358-202611080003}"
#define NombreApp "ConverterSmartGrid - QA aislada"
#define DirectorioApp "D:\converter\auditorias\csg_qa_1108"
#define NombreAcceso "ConverterSmartGrid QA"
#else
#define IdentidadApp "{{6F0B1C52-8A3E-4C57-9B0E-6F4C2D7A1E86}"
#define NombreApp "ConverterSmartGrid"
#define DirectorioApp "{localappdata}\Programs\ConverterSmartGrid"
#define NombreAcceso "ConverterSmartGrid"
#endif

[Setup]
AppId={#IdentidadApp}
AppName={#NombreApp}
AppVersion={#Version}
DefaultDirName={#DirectorioApp}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
#ifdef EnsayoQA
OutputBaseFilename=ConverterSmartGrid-{#Version}-qa-setup
#else
OutputBaseFilename=ConverterSmartGrid-{#Version}-setup
#endif
OutputDir={#SourcePath}\salida
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Actualizar deja la versión anterior instalada para poder volver: no se cierra nada por sorpresa.
CloseApplications=no
UninstallDisplayName={#NombreApp}
; RF-58: quien actualiza sigue en su carpeta, con la versión anterior a la que volver al lado. Con «no», un operador que
; eligió otra carpeta acabaría con dos programas y sin vuelta atrás. Lo que no se reutiliza (una carpeta en la temporal,
; o que ya no tiene el programa: el rc5 se instaló en %TEMP%\csgp, la de un ensayo del rc1) lo decide InitializeWizard.
UsePreviousAppDir=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"

[Files]
; El candidato se deja en una carpeta temporal del programa, y se borra al terminar.
Source: "{#Candidato}\*"; DestDir: "{app}\_entrega"; Flags: recursesubdirs createallsubdirs ignoreversion deleteafterinstall

[Icons]
Name: "{autoprograms}\{#NombreAcceso}"; Filename: "{app}\ConverterSmartGrid.cmd"
Name: "{autodesktop}\{#NombreAcceso}"; Filename: "{app}\ConverterSmartGrid.cmd"; Tasks: escritorio
Name: "{autoprograms}\{#NombreAcceso} - diagnostico"; Filename: "{cmd}"; Parameters: "/k ""{app}\csg.cmd"" doctor"

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
const
  { RF-57: instalar_candidato.py corre oculto; lo que dice en su consola se perdía y el registro solo tenía «1».
    Con --registro deja aquí su motivo (UTF-8 con BOM), y este guion lo lee. }
  FicheroMotivo = 'motivo_instalacion.txt';

var
  FalloInstalacion: Boolean;

function DentroDe(const Carpeta, Raiz: String): Boolean;
begin
  Result := (Raiz <> '') and (Pos(Lowercase(AddBackslash(Raiz)), Lowercase(AddBackslash(Carpeta))) = 1);
end;

procedure InitializeWizard;
var
  Previa, Motivo: String;
begin
  { RF-58: UsePreviousAppDir deja en la carpeta de la instalación registrada. Sirve si es una instalación de verdad;
    una carpeta en la temporal de Windows (que se limpia) o sin actual.txt (sin el programa) no lo es. /DIR manda. }
  Previa := WizardForm.DirEdit.Text;
  if (ExpandConstant('{param:DIR|}') <> '') or
      (CompareText(RemoveBackslash(Previa), RemoveBackslash(ExpandConstant('{#DirectorioApp}'))) = 0) then
    Exit;
  Motivo := '';
  if DentroDe(Previa, GetEnv('TEMP')) or DentroDe(Previa, GetEnv('TMP')) or
      DentroDe(Previa, ExpandConstant('{localappdata}\Temp')) then
    Motivo := 'esta en la carpeta temporal de Windows'
  else if not FileExists(AddBackslash(Previa) + 'actual.txt') then
    Motivo := 'ya no tiene el programa';
  if Motivo <> '' then
  begin
    { Una línea de [Code] que empieza por corchete se lee como sección: los argumentos van en la misma línea. }
    Log(Format('La instalacion anterior registrada en %s %s: se instala en %s.', [Previa, Motivo,
      ExpandConstant('{#DirectorioApp}')]));
    WizardForm.DirEdit.Text := ExpandConstant('{#DirectorioApp}');
  end;
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
      begin
        if Result <> '' then
          Result := Result + #13#10;
        Result := Result + Trim(Lineas[I]);
      end;
end;

procedure ComprobarInstalacion;
var
  CodigoProceso: Integer;
  VersionActiva: AnsiString;
  Motivo: String;
begin
  { RF-39: una carpeta anterior no salva un proceso fallido. El guion Python
    conserva el puntero anterior si falla; el contenedor debe devolver error. }
  FalloInstalacion := True;
  CodigoProceso := -1;
  Motivo := '';
  DeleteFile(ExpandConstant('{tmp}\' + FicheroMotivo));
  WizardForm.StatusLabel.Caption := 'Comprobando las huellas e instalando...';
  if Exec(ExpandConstant('{app}\_entrega\terceros\python\python.exe'),
      ExpandConstant('"{app}\_entrega\instalador\instalar_candidato.py" instalar --candidato "{app}\_entrega" --destino "{app}"'
        + ' --registro "{tmp}\' + FicheroMotivo + '"'),
      '', SW_HIDE, ewWaitUntilTerminated, CodigoProceso) then
  begin
    Log(Format('Resultado de instalar_candidato.py: %d', [CodigoProceso]));
    if (CodigoProceso = 0) and
        FileExists(ExpandConstant('{app}\versiones\{#Version}\python\python.exe')) and
        LoadStringFromFile(ExpandConstant('{app}\actual.txt'), VersionActiva) then
      FalloInstalacion := Trim(String(VersionActiva)) <> '{#Version}';
    if FalloInstalacion then
      Motivo := MotivoDelFallo;
  end
  else
  begin
    Log(Format('No se pudo iniciar instalar_candidato.py: %d', [CodigoProceso]));
    Motivo := 'No se pudo iniciar el Python del paquete: ' + SysErrorMessage(CodigoProceso);
  end;
  if FalloInstalacion then
  begin
    if Motivo = '' then
      Motivo := Format('instalar_candidato.py termino con el codigo %d sin dejar su motivo.', [CodigoProceso]);
    Log('No se pudo terminar la instalacion. Se conserva el programa anterior. Motivo: ' + Motivo);
    { Tambien con /VERYSILENT: el operador que actualiza en silencio tiene que saber por que no cambio nada. Quien
      automatiza la instalacion lo calla con /SUPPRESSMSGBOXES, y el motivo sigue en el registro. }
    SuppressibleMsgBox('No se pudo terminar la instalacion. Lo que hubiera instalado sigue igual.' + #13#10#13#10 + Motivo,
      mbError, MB_OK, IDOK);
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
