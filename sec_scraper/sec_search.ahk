#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; SEC Search Script - Browser restart approach
; Closes and reopens browser for each contractor (slower but more reliable)
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

; Process each contractor
Loop, % contractors.MaxIndex() {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    if FileExist(resultFile)
        continue

    ; Open browser for this contractor
    Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
    WinWaitActive, ahk_class Chrome_WidgetWin_1, , 10
    if ErrorLevel
        continue

    WinMaximize
    Sleep, 5000  ; Initial page load - keep long

    ; Navigate to search field
    Click, 1, 1
    Sleep, 100
    Loop, 9 {
        Send, {Tab}
        Sleep, 50
    }

    ; Perform search
    Send, %contractorName%
    Sleep, 100
    Send, {Tab}
    Sleep, 50
    Send, {Space}
    Sleep, 8000  ; Wait for search results - keep long

    ; Copy results
    Send, ^a
    Sleep, 100
    Send, ^c
    Sleep, 200

    ; Save to file
    FileCreateDir, sec_results
    FileAppend, %Clipboard%, %resultFile%

    ; Close browser
    WinClose, ahk_class Chrome_WidgetWin_1
    Sleep, 500
}

ExitApp