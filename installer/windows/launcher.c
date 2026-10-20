/* Cyclara.exe: the program behind the Start menu entry, the Desktop icon and "Open with".
 *
 * It hosts the bundled CPython in this process (python\python312.dll), so the window,
 * the taskbar button, Task Manager and a pinned shortcut all belong to Cyclara.exe and
 * not to a stray pythonw.exe. Nothing else lives here: the interpreter is pointed at
 * the bundled runtime and asked to run electrochem.studio, the same module the
 * Setup.bat installation runs.
 *
 *   Cyclara.exe [file ...]      open Cyclara, with those files
 *   Cyclara.exe -<python opts>  behave exactly like python.exe (Python itself does this
 *                               when it starts a helper process to read a file)
 *   Cyclara.exe --no-intro ...  Cyclara's own double-dash options go to the app
 *
 * A window program has no console, so electrochem.studio writes its messages and any
 * traceback to %LOCALAPPDATA%\Cyclara\cyclara.log; the message box shown when Python
 * returns an error names that file.
 *
 * Built from Linux with mingw-w64 (installer/build.py); no Windows SDK is needed because
 * python312.dll is loaded at run time and only two of its functions are used.
 */
#include <windows.h>
#include <shlobj.h>
#include <wchar.h>

typedef void (*SetHomeFn)(const wchar_t *);
typedef int (*MainFn)(int, wchar_t **);

static void fail(const wchar_t *text)
{
    MessageBoxW(NULL, text, L"Cyclara", MB_OK | MB_ICONERROR);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmdline, int show)
{
    (void)inst; (void)prev; (void)cmdline; (void)show;
    wchar_t exe[MAX_PATH], home[MAX_PATH], dll[MAX_PATH], log[MAX_PATH] = L"%LOCALAPPDATA%\\Cyclara\\cyclara.log";
    if (!GetModuleFileNameW(NULL, exe, MAX_PATH)) {
        fail(L"Cyclara could not find its own folder.");
        return 1;
    }
    wchar_t *slash = wcsrchr(exe, L'\\');
    if (slash)
        *slash = 0;                                  /* exe now holds the installation folder */
    swprintf(home, MAX_PATH, L"%ls\\python", exe);
    swprintf(dll, MAX_PATH, L"%ls\\python312.dll", home);
    wchar_t local[MAX_PATH];
    if (SUCCEEDED(SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, local)))
        swprintf(log, MAX_PATH, L"%ls\\Cyclara\\cyclara.log", local);

    /* The bundled runtime's own folder comes first for DLL resolution. */
    SetDllDirectoryW(home);
    HMODULE py = LoadLibraryW(dll);
    if (!py) {
        wchar_t msg[600];
        swprintf(msg, 600, L"Cyclara's Python runtime is missing or damaged:\n%ls\n\nRun the Cyclara installer again.", dll);
        fail(msg);
        return 2;
    }
    SetHomeFn set_home = (SetHomeFn)GetProcAddress(py, "Py_SetPythonHome");
    MainFn py_main = (MainFn)GetProcAddress(py, "Py_Main");
    if (!set_home || !py_main) {
        fail(L"Cyclara's Python runtime is not the expected version. Run the installer again.");
        return 2;
    }
    set_home(home);

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) {
        fail(L"Cyclara could not read its command line.");
        return 1;
    }
    /* Python's own options are single-dash (-c, -m, -I, -X ...); Cyclara's are double-dash (--no-intro). */
    int passthrough = argc > 1 && argv[1][0] == L'-' && argv[1][1] != L'-';
    wchar_t **args = (wchar_t **)LocalAlloc(LPTR, sizeof(wchar_t *) * (argc + 8));
    int n = 0;
    args[n++] = argv[0];
    if (passthrough) {
        /* Python options first: this is Python itself starting a helper, or a power user. */
        for (int k = 1; k < argc; k++)
            args[n++] = argv[k];
    } else {
        args[n++] = L"-I";                           /* isolated: no PYTHONPATH, no user site */
        args[n++] = L"-X"; args[n++] = L"utf8";
        args[n++] = L"-m"; args[n++] = L"electrochem.studio";
        for (int k = 1; k < argc; k++)
            args[n++] = argv[k];
    }
    int code = py_main(n, args);
    if (code != 0 && !passthrough) {
        wchar_t msg[700];
        swprintf(msg, 700, L"Cyclara stopped with an error (code %d).\n\nWhat went wrong is written in\n%ls\n\n"
                           L"If that file is empty, run the Cyclara installer again.", code, log);
        fail(msg);
    }
    return code;
}
