Option Explicit
Dim sh, fso, base, target, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
target = Chr(34) & base & "\gph_central.py" & Chr(34)

' Inicia a Central sem janela de console. O executável Windows final também usa no-console.
On Error Resume Next
Err.Clear
rc = sh.Run("pyw.exe -3 " & target, 0, False)
If Err.Number = 0 Then WScript.Quit 0
Err.Clear
rc = sh.Run("pythonw.exe " & target, 0, False)
If Err.Number = 0 Then WScript.Quit 0
On Error GoTo 0

MsgBox "Não foi possível localizar Python para iniciar a GP-H Central Histórica." & vbCrLf & _
       "Quando a distribuição .exe for gerada, Python não será necessário.", _
       vbExclamation, "GP-H Central Histórica"
