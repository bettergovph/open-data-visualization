#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; SEC Search Script - Simple version
; Processes 10 contractors, saves raw results for Python parser

#Include contractor_list_1000.txt

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