; Cyclara Windows installer (NSIS 3, Modern UI 2).
;
; One program folder per user, no administrator prompt, no choices a researcher
; should not have to make: Welcome -> where -> installing -> open Cyclara.
; Everything the app needs is inside the installer: the bundled CPython, the
; scientific packages, Qt and Cyclara itself. Nothing is downloaded.
;
; Built by installer/build.py, which passes:
;   /DVERSION=0.7.0            the version shown everywhere
;   /DSTAGE=<dir>              the staged tree: Cyclara.exe, python\, app\
;   /DART=<dir>                welcome.bmp, header.bmp, cyclara.ico
;   /DOUT=<file>               the installer to write
;   /DSIZE_KB=<n>              installed size, for Apps & features

Unicode true
ManifestDPIAware true
ManifestSupportedOS all
SetCompressor /SOLID lzma
SetCompressorDictSize 64
RequestExecutionLevel user

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"

!define NAME "Cyclara"
!define PUBLISHER "Aswadh Shyma Sajeevan"
!define URL "https://github.com/asajeevan/electrochem-toolkit"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}"
!define APPS_KEY "Software\Classes\Applications\Cyclara.exe"
!define PROGID "Cyclara.Measurement"

Name "${NAME} ${VERSION}"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\Programs\${NAME}"
InstallDirRegKey HKCU "Software\${NAME}" "InstallDir"
BrandingText "${NAME} ${VERSION}   free software, GPL-3.0-or-later"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${NAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${NAME} ${VERSION} installer"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "GPL-3.0-or-later"

; ---- look --------------------------------------------------------------------
!define MUI_ICON "${ART}\cyclara.ico"
!define MUI_UNICON "${ART}\cyclara.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${ART}\welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${ART}\welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${ART}\header.bmp"
!define MUI_HEADERIMAGE_UNBITMAP "${ART}\header.bmp"
!define MUI_BGCOLOR "FFFFFF"
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "Stop installing ${NAME}?"

; ---- pages -------------------------------------------------------------------
!define MUI_WELCOMEPAGE_TITLE "Cyclara"
!define MUI_WELCOMEPAGE_TITLE_3LINES
!define MUI_WELCOMEPAGE_TEXT "Cycling analysis for battery research: open a cycler's file, answer only what the file cannot say, and take away publication figures and tables.$\r$\n$\r$\nThis installs Cyclara ${VERSION} for your user account. No administrator password is needed and nothing else on this computer is changed.$\r$\n$\r$\nCyclara is free software (GPL-3.0-or-later)."
!insertmacro MUI_PAGE_WELCOME

!define MUI_DIRECTORYPAGE_TEXT_TOP "Cyclara will be installed in the folder below. Install is fine for almost everyone; choose another folder only if this drive is short of space (about ${SIZE_MB} MB is needed)."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "Install folder"
!insertmacro MUI_PAGE_DIRECTORY

!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "Installed"
!define MUI_INSTFILESPAGE_FINISHHEADER_SUBTEXT "Cyclara ${VERSION} is ready."
!define MUI_INSTFILESPAGE_ABORTHEADER_TEXT "Not installed"
!define MUI_INSTFILESPAGE_ABORTHEADER_SUBTEXT "Installation was stopped before it finished."
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "Cyclara is ready"
!define MUI_FINISHPAGE_TITLE_3LINES
!define MUI_FINISHPAGE_TEXT "Cyclara is in the Start menu and on the Desktop.$\r$\n$\r$\nDrop a cycling file or a whole folder onto its window; it asks only what the file cannot say. The demonstration under Help shows every step."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Cyclara.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Cyclara now"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\app\HOW_TO_USE.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Show the short guide"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_NOREBOOTSUPPORT
!insertmacro MUI_PAGE_FINISH

!define MUI_WELCOMEPAGE_TITLE "Remove Cyclara"
!define MUI_WELCOMEPAGE_TEXT "This removes Cyclara ${VERSION} from your account: the program folder, the Start menu entry and the Desktop icon.$\r$\n$\r$\nYour measurement files, the analysis folders Cyclara wrote next to them, and your saved settings and import profiles are left alone."
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "Cyclara was removed"
!define MUI_FINISHPAGE_TEXT "Thank you for trying it. Settings and saved import profiles stay in your user folder in case you install Cyclara again."
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ---- helpers -----------------------------------------------------------------
Function .onInit
  ; A previous Cyclara in the same folder is replaced cleanly: its program files go first,
  ; nothing of the user's is touched (settings and profiles live under %APPDATA%).
  ReadRegStr $0 HKCU "Software\${NAME}" "InstallDir"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
FunctionEnd

; ---- install -----------------------------------------------------------------
!macro Say text
  SetDetailsPrint textonly
  DetailPrint "${text}"
  SetDetailsPrint none
!macroend

Section "Cyclara" SecMain
  SectionIn RO
  SetDetailsPrint none
  !insertmacro Say "Closing an open Cyclara, if any..."
  ; Files in use would stop the copy; ask a running Cyclara to close first.
  FindWindow $0 "" "Cyclara"
  ${If} $0 != 0
    SendMessage $0 ${WM_CLOSE} 0 0
    Sleep 1500
  ${EndIf}

  !insertmacro Say "Removing the previous version..."
  ${If} ${FileExists} "$INSTDIR\Cyclara.exe"
    RMDir /r "$INSTDIR\python"
    RMDir /r "$INSTDIR\app"
    Delete "$INSTDIR\Cyclara.exe"
    Delete "$INSTDIR\Uninstall.exe"
  ${EndIf}

  !insertmacro Say "Copying Cyclara ${VERSION} (this takes a minute)..."
  SetOutPath "$INSTDIR"
  File "${STAGE}\Cyclara.exe"
  File "${STAGE}\*.dll"
  File "${STAGE}\LICENSE"
  File /r "${STAGE}\python"
  File /r "${STAGE}\app"

  !insertmacro Say "Creating shortcuts..."
  CreateShortcut "$SMPROGRAMS\${NAME}.lnk" "$INSTDIR\Cyclara.exe" "" "$INSTDIR\Cyclara.exe" 0 SW_SHOWNORMAL "" "Cycling analysis for battery research"
  CreateShortcut "$DESKTOP\${NAME}.lnk" "$INSTDIR\Cyclara.exe" "" "$INSTDIR\Cyclara.exe" 0 SW_SHOWNORMAL "" "Cycling analysis for battery research"

  !insertmacro Say "Registering with Windows..."
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${NAME}" "Version" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\Cyclara.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "URLInfoAbout" "${URL}"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" ${SIZE_KB}

  ; "Open with" lists Cyclara for measurement files without taking any default away.
  WriteRegStr HKCU "${APPS_KEY}" "FriendlyAppName" "${NAME}"
  WriteRegStr HKCU "${APPS_KEY}\DefaultIcon" "" "$INSTDIR\Cyclara.exe,0"
  WriteRegStr HKCU "${APPS_KEY}\shell\open" "FriendlyAppName" "${NAME}"
  WriteRegStr HKCU "${APPS_KEY}\shell\open\command" "" '"$INSTDIR\Cyclara.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\${PROGID}" "" "Cycling measurement"
  WriteRegStr HKCU "Software\Classes\${PROGID}" "FriendlyTypeName" "Cycling measurement"
  WriteRegStr HKCU "Software\Classes\${PROGID}\DefaultIcon" "" "$INSTDIR\Cyclara.exe,0"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\open" "" "Open with ${NAME}"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\open\command" "" '"$INSTDIR\Cyclara.exe" "%1"'
  !macro OpenWith ext
    WriteRegStr HKCU "${APPS_KEY}\SupportedTypes" "${ext}" ""
    WriteRegStr HKCU "Software\Classes\${ext}\OpenWithProgids" "${PROGID}" ""
  !macroend
  !insertmacro OpenWith ".mpr"
  !insertmacro OpenWith ".mpt"
  !insertmacro OpenWith ".cex"
  !insertmacro OpenWith ".csv"
  !insertmacro OpenWith ".txt"
  !insertmacro OpenWith ".xlsx"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
  !insertmacro Say "Done."
SectionEnd

; ---- uninstall ---------------------------------------------------------------
Section "Uninstall"
  FindWindow $0 "" "Cyclara"
  ${If} $0 != 0
    SendMessage $0 ${WM_CLOSE} 0 0
    Sleep 1500
  ${EndIf}
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\Cyclara.exe"
  Delete "$INSTDIR\*.dll"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\${NAME}.lnk"
  Delete "$DESKTOP\${NAME}.lnk"
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "${APPS_KEY}"
  DeleteRegKey HKCU "Software\Classes\${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.mpr\OpenWithProgids" "${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.mpt\OpenWithProgids" "${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.cex\OpenWithProgids" "${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.csv\OpenWithProgids" "${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.txt\OpenWithProgids" "${PROGID}"
  DeleteRegValue HKCU "Software\Classes\.xlsx\OpenWithProgids" "${PROGID}"
  DeleteRegKey HKCU "Software\${NAME}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
