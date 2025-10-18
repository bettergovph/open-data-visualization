#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

MsgBox, Script started

FileRead, contractorData, contractor_list_top100_no_sec.txt
if ErrorLevel {
    MsgBox, Failed to read file
    ExitApp
}

MsgBox, File read successfully

RegExMatch(contractorData, "contractors := \[(.*)\]", match)
if (!match) {
    MsgBox, Failed to parse
    ExitApp
}

contractors := []
Loop, Parse, match1, `"
{
    cleaned := Trim(A_LoopField)
    cleaned := StrReplace(cleaned, ",", "")
    cleaned := Trim(cleaned)
    if (cleaned != "" && StrLen(cleaned) > 5)
        contractors.Push(cleaned)
}

MsgBox, Parsed %contractors.MaxIndex()% contractors. Press OK to start processing.

Loop, % contractors.MaxIndex() {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    if FileExist(resultFile)
        continue

    Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
    Sleep, 7000

    Click, 1, 1
    Sleep, 200
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

    Clipboard := ""
    Send, ^a
    Sleep, 100
    Send, ^c
    Sleep, 200

    FileCreateDir, sec_results
    FileAppend, %Clipboard%, %resultFile%
    Clipboard := ""

    WinClose, ahk_class Chrome_WidgetWin_1
    Sleep, 1000
}

MsgBox, Complete!
ExitApp

