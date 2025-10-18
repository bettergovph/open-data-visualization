#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

FileRead, contractorData, contractor_list_top100_no_sec.txt
if ErrorLevel
    ExitApp

RegExMatch(contractorData, "contractors := \[(.*)\]", match)
if (!match)
    ExitApp

contractors := []
Loop, Parse, match1, `"
{
    cleaned := Trim(A_LoopField)
    cleaned := StrReplace(cleaned, ",", "")
    cleaned := Trim(cleaned)
    if (cleaned != "" && StrLen(cleaned) > 5)
        contractors.Push(cleaned)
}

Loop, % contractors.MaxIndex() {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    if FileExist(resultFile)
        continue

    Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
    WinWaitActive, ahk_class Chrome_WidgetWin_1, , 10
    if ErrorLevel
        continue

    Sleep, 5000

    Click, 1, 1
    Sleep, 100
    Loop, 9 {
        Send, {Tab}
        Sleep, 50
    }

    Send, %contractorName%
    Sleep, 100
    Send, {Tab}
    Sleep, 50
    Send, {Space}
    Sleep, 8000

    Send, ^a
    Sleep, 100
    Send, ^c
    Sleep, 200

    FileCreateDir, sec_results
    FileAppend, %Clipboard%, %resultFile%

    WinClose, ahk_class Chrome_WidgetWin_1
    Sleep, 500
}

ExitApp