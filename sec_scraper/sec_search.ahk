#NoEnv
SendMode Input
SetWorkingDir %A_ScriptDir%

; Read contractors from file
contractors := []
FileRead, fileContent, contractor_list_retry.txt
if ErrorLevel
{
    MsgBox, Cannot read contractor list file
    ExitApp
}

; Parse each line as a contractor name
Loop, Parse, fileContent, `n, `r
{
    cleaned := Trim(A_LoopField)
    if (cleaned != "" && StrLen(cleaned) > 2)
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

count := 0

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
    Sleep, 12000

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

           count := count + 1
           
           if (count = 2) {
               Process, Close, msedge.exe
               Sleep, 3000
               Run msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index
               Sleep, 7000
               Click, 1, 1
               Sleep, 200
               Loop, 9 {
                   Send, {Tab}
                   Sleep, 50
               }
               count := 0
           }
}

Process, Close, msedge.exe
ExitApp