#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; Test script - verifies page load before proceeding
; Opens browser, waits, then checks if we can type

Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
Sleep, 6000

; Click and try to tab to search field
Click, 1, 1
Sleep, 200
Loop, 9 {
    Send, {Tab}
    Sleep, 50
}

; Type test string
Send, TEST CONTRACTOR
Sleep, 500

; Show what's in clipboard after selecting all
Send, ^a
Sleep, 200
Send, ^c
Sleep, 200

MsgBox, Clipboard contains: %Clipboard%

ExitApp

