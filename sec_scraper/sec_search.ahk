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

    Send, ^a
    Sleep, 100
    Send, ^c
    Sleep, 200

    FileCreateDir, sec_results
    FileAppend, %Clipboard%, %resultFile%

    Process, Close, msedge.exe
    Sleep, 500
}

ExitApp