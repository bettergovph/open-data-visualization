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

Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
Sleep, 7000

Click, 1, 1
Sleep, 200
Loop, 9 {
    Send, {Tab}
    Sleep, 50
}

processedCount := 0

Loop, % contractors.MaxIndex() {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    if FileExist(resultFile)
        continue

    Send, ^a
    Sleep, 50
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

    Send, {Escape}
    Sleep, 100
    Send, {Shift Down}{Tab}{Shift Up}
    Sleep, 100

    processedCount++
    
    if (Mod(processedCount, 5) = 0) {
        Send, !{F4}
        Sleep, 1000
        Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
        Sleep, 7000
        Click, 1, 1
        Sleep, 200
        Loop, 9 {
            Send, {Tab}
            Sleep, 50
        }
    }
}

Send, !{F4}
ExitApp