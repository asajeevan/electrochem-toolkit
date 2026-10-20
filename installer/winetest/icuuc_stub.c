/* Test-only stub of Windows' system ICU converter API, so Qt6Core.dll loads under Wine 9.
   Qt only reaches these through QStringConverter for codecs it has no built-in table for;
   every call fails cleanly. Never shipped: Windows 10 1903 and later carry the real icuuc.dll. */
#include <stddef.h>
#define X __declspec(dllexport)
X void *ucnv_open(const char *n, int *err) { if (err) *err = 4; return NULL; }   /* U_FILE_ACCESS_ERROR */
X void ucnv_close(void *c) {}
X void UCNV_FROM_U_CALLBACK_SUBSTITUTE(void) {}
X void UCNV_TO_U_CALLBACK_SUBSTITUTE(void) {}
X void ucnv_reset(void *c) {}
X signed char ucnv_getMaxCharSize(const void *c) { return 1; }
X const char *ucnv_getName(const void *c, int *err) { return ""; }
X void ucnv_getToUCallBack(const void *c, void **a, const void **b) {}
X void ucnv_getFromUCallBack(const void *c, void **a, const void **b) {}
X void ucnv_setToUCallBack(void *c, void *a, const void *b, void **oa, const void **ob, int *err) {}
X void ucnv_setFromUCallBack(void *c, void *a, const void *b, void **oa, const void **ob, int *err) {}
X void ucnv_cbToUWriteUChars(void *a, const unsigned short *s, int n, int off, int *err) {}
X void ucnv_toUnicode(void *c, unsigned short **t, const unsigned short *tl, const char **s, const char *sl, int *o, signed char f, int *err) { if (err) *err = 1; }
X void ucnv_cbFromUWriteUChars(void *a, const unsigned short **s, const unsigned short *sl, int off, int *err) {}
X int ucnv_toUCountPending(const void *c, int *err) { return 0; }
X int ucnv_fromUCountPending(const void *c, int *err) { return 0; }
X const char *ucnv_getStandardName(const char *n, const char *s, int *err) { return NULL; }
X const char *ucnv_getAvailableName(int n) { return NULL; }
X int ucnv_countAvailable(void) { return 0; }
X void ucnv_fromUnicode(void *c, char **t, const char *tl, const unsigned short **s, const unsigned short *sl, int *o, signed char f, int *err) { if (err) *err = 1; }
