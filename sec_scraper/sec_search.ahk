#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; Configuration
BROWSER_RESTART_INTERVAL := 2  ; Restart browser every N searches
SEARCH_DELAY := 12000          ; Wait time for search results (12 seconds)
BROWSER_START_DELAY := 7000    ; Wait time for browser to start

; Read contractors from file
contractors := []
FileRead, fileContent, contractor_list_top2000_unprocessed.txt
if ErrorLevel
{
    MsgBox, Cannot read contractor list file. Make sure contractor_list_top2000_unprocessed.txt exists.
    ExitApp
}

; Parse each line as a contractor name
Loop, Parse, fileContent, `n, `r
{
    cleaned := Trim(A_LoopField)
    if (cleaned != "" && StrLen(cleaned) > 2)
        contractors.Push(cleaned)
}

totalContractors := contractors.MaxIndex()
MsgBox, 4, Fresh Contractor List, Found %totalContractors% contractors. Start SEC scraping?
IfMsgBox No
    ExitApp

; Create results directory
FileCreateDir, sec_results

; Start browser
Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
Sleep, %BROWSER_START_DELAY%

; Navigate to search field
Click, 1, 1
Sleep, 200
Loop, 9 {
    Send, {Tab}
    Sleep, 50
}

count := 0
processed := 0
skipped := 0

Loop, % totalContractors {
    contractorName := contractors[A_Index]
    resultFile := "sec_results\" . StrReplace(contractorName, " ", "_") . ".txt"

    ; Skip if already processed
    if FileExist(resultFile) {
        skipped++
        continue
    }

    ; Clear search field and enter contractor name
    Send, ^a
    Sleep, 50
    Send, %contractorName%
    Sleep, 100
    Send, {Tab}
    Sleep, 50
    Send, {Space}
    Sleep, %SEARCH_DELAY%

    ; Copy results
    Clipboard := ""
    Send, ^a
    Sleep, 100
    Send, ^c
    Sleep, 200

    ; Save results to file
    FileAppend, %Clipboard%, %resultFile%
    Clipboard := ""

    ; Clear search for next iteration
    Send, {Escape}
    Sleep, 100
    Send, {Shift Down}{Tab}{Shift Up}
    Sleep, 100

    count++
    processed++

    ; Show progress
    if (Mod(count, 10) = 0) {
        progress := Round((count / totalContractors) * 100, 1)
        ToolTip, Progress: %count%/%totalContractors% (%progress%%)`nProcessed: %processed%`nSkipped: %skipped%
    }

    ; Restart browser periodically to avoid memory issues
    if (count = BROWSER_RESTART_INTERVAL) {
        Process, Close, msedge.exe
        Sleep, 3000
        
        ; Restart browser
        Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
        Sleep, %BROWSER_START_DELAY%
        
        ; Navigate to search field again
        Click, 1, 1
        Sleep, 200
        Loop, 9 {
            Send, {Tab}
            Sleep, 50
        }
        
        count := 0
    }
}

; Final cleanup
Process, Close, msedge.exe
ToolTip, 

; Show completion message
MsgBox, 0, SEC Scraping Complete, SEC scraping completed!`n`nProcessed: %processed% contractors`nSkipped: %skipped% contractors`nTotal: %totalContractors% contractors

ExitApp