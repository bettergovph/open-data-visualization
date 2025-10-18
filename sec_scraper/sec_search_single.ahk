#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; --- Configuration ---
companyName := "legacy construction"
secUrl := "https://checkwithsec.sec.gov.ph/check-with-sec/index"
browserExe := "msedge.exe"

; --- Main Script ---
Run %browserExe% --new-window %secUrl%
WinWaitActive, ahk_class Chrome_WidgetWin_1, , 10
if ErrorLevel {
    MsgBox, 16, Error, Failed to open Edge or navigate to SEC site.
    ExitApp
}

WinMaximize
Sleep, 5000 ; Wait 5 seconds for page load

; Activate browser window
WinActivate, ahk_class Chrome_WidgetWin_1

; Click on page at position 1,1
Click, 1, 1
Sleep, 1000

; Tab exactly 9 times to reach search input
Loop, 9 {
    Send, {Tab}
    Sleep, 300
}

; Now type the company name
Send, %companyName%
Sleep, 500

; Tab once more to reach search button and click it
Send, {Tab}
Sleep, 300
Send, {Space} ; Click the search button

Sleep, 8000 ; Wait 8 seconds for results

; Copy results
Send, ^a ; Select all
Sleep, 500
Send, ^c ; Copy
Sleep, 500

; Save results
FileDelete, SEC_SearchResults.txt
FileAppend, %Clipboard%, SEC_SearchResults.txt
MsgBox, 64, Success, Search results saved to SEC_SearchResults.txt

; Close browser
WinClose, ahk_class Chrome_WidgetWin_1
ExitApp