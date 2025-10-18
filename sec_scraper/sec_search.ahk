#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; SEC Search Script - Simple version
; Processes top 100 contractors without SEC data
; Saves raw results for Python parser

; Read contractor list from file
FileRead, contractorData, contractor_list_top100_no_sec.txt
if ErrorLevel {
    MsgBox, 16, Error, Failed to read contractor_list_top100_no_sec.txt
    ExitApp
}

; Parse the contractor array from file
; Extract the array content between [ and ]
RegExMatch(contractorData, "contractors := \[(.*)\]", match)
if (!match) {
    MsgBox, 16, Error, Failed to parse contractor list
    ExitApp
}

; Build contractors array
contractors := []
arrayContent := match1

; Split by quotes and extract contractor names
Loop, Parse, arrayContent, `"
{
    cleaned := Trim(A_LoopField)
    cleaned := StrReplace(cleaned, ",", "")
    cleaned := Trim(cleaned)
    if (cleaned != "" && StrLen(cleaned) > 5)
        contractors.Push(cleaned)
}

; Open browser
Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
WinWaitActive, ahk_class Chrome_WidgetWin_1, , 10
if ErrorLevel
    ExitApp

WinMaximize
Sleep, 5000

; Navigate to search field once at start
Click, 1, 1
Sleep, 1000
Loop, 9 {
    Send, {Tab}
    Sleep, 300
}

; Process each contractor
Loop, % contractors.MaxIndex() {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    if FileExist(resultFile)
        continue

    ; Reset mouse to top-left corner to prevent scrolling issues
    MouseMove, 1, 1
    Sleep, 300

    Send, ^a
    Sleep, 200
    Send, %contractorName%
    Sleep, 1000
    Send, {Tab}
    Sleep, 300
    Send, {Space}
    Sleep, 8000

    Send, ^a
    Sleep, 500
    Send, ^c
    Sleep, 500

    FileCreateDir, sec_results
    FileAppend, %Clipboard%, %resultFile%

    Send, {Escape}
    Sleep, 200
    Send, {Shift Down}{Tab}{Shift Up}
    Sleep, 300

    TrayTip, Done, %contractorName%, 2
}

WinClose, ahk_class Chrome_WidgetWin_1
ExitApp