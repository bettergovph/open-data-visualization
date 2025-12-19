#NoEnv
#Requires AutoHotkey v1.1.33+
SendMode Input
CoordMode, Mouse, Window
SetWorkingDir %A_ScriptDir%\..

; Generates `repeated_projects_report.md` from `repeated_targets.json` and (optionally)
; automates screenshots for each DPWH transparency contract.
;
; Output images:
; - screenshots/<contract_id>_portal.png
; - screenshots/<contract_id>_gallery.png

INPUT_JSON := "repeated_targets.json"
OUTPUT_MD := "repeated_projects_report.md"
SCREENSHOTS_DIR := "screenshots"
CONTRACT_LIST_FILE := A_ScriptDir . "\contract_list_top100.txt"
INI_FILE := A_ScriptDir . "\generate_report.ini"

; Limits (set to 0 for "all")
MAX_PROJECTS := 100
MAX_CONTRACTS := 100

; Browser automation settings (coordinate-based)
PAGE_LOAD_SLEEP_MS := 8000
GALLERY_LOAD_SLEEP_MS := 2500
GALLERY_CLICK_X := 350
GALLERY_CLICK_Y := 215
GALLERY_SCROLL_WHEELDOWN := 12
GALLERY_FALLBACK_TAB_COUNT := 18
GALLERY_USE_TAB_FALLBACK := false
RESTART_BROWSER_EVERY := 5

; Tips:
; - Use `F2` while Edge is active to save Gallery click coordinates to `scripts/generate_report.ini`.
; - If click still fails, set `gallery_use_tab_fallback=1` in the INI and tune `gallery_fallback_tab_count`.

; Set false to only generate markdown (no screenshots)
TAKE_SCREENSHOTS := true


LoadConfig()

if (!FileExist(INPUT_JSON)) {
    MsgBox, 16, Missing Input, % "Cannot find " INPUT_JSON " in " A_WorkingDir "."
    ExitApp
}

FileRead, jsonText, %INPUT_JSON%
if (ErrorLevel) {
    MsgBox, 16, Read Error, % "Failed to read " INPUT_JSON "."
    ExitApp
}

targets := JsonParse(jsonText)
totalProjects := targets.length
if (totalProjects <= 0) {
    MsgBox, 16, Parse Error, % INPUT_JSON " appears empty or invalid."
    ExitApp
}

projectLimit := LimitCount(totalProjects, MAX_PROJECTS)

contractIds := []
seenContracts := {}

md := FileOpen(OUTPUT_MD, "w", "UTF-8")
if (!IsObject(md)) {
    MsgBox, 16, Write Error, % "Failed to open " OUTPUT_MD " for writing."
    ExitApp
}

md.Write("# Repeated Projects Report (2026 Integration)`n`n")
md.Write("**Generated At:** " . NowTimestamp() . "`n")
md.Write("**Total Projects:** " . projectLimit . "`n`n")
md.Write("---`n`n")

Loop, % projectLimit {
    p := JsArrayAt(targets, A_Index - 1)
    pid := "" . p.id
    name := "" . p.name
    histMatch := "" . p.historical_match
    if (histMatch = "" || histMatch = "undefined" || histMatch = "null") {
        histMatch := "N/A"
    }
    links := p.transparency_links

    md.Write("## " . name . "`n`n")
    md.Write("- **Project ID:** `" . pid . "`" . "`n")
    md.Write("- **Historical Match Trigger:** " . histMatch . "`n`n")

    linkCount := (IsObject(links) ? links.length : 0)
    if (linkCount > 0) {
        md.Write("### Matched Transparency Contracts (" . linkCount . ")`n`n")
        Loop, % linkCount {
            link := JsArrayAt(links, A_Index - 1)
            cid := "" . link.id
            cname := "" . link.name
            camount := FormatCurrency(link.amount)
            url := "https://transparency.dpwh.gov.ph/?project=" . cid

            md.Write("#### Contract: [" . cid . "](" . url . ")`n")
            md.Write("- **Contract Name:** " . cname . "`n")
            md.Write("- **Amount:** " . camount . "`n`n")

            md.Write("**Portal View:**`n")
            md.Write("![Portal View " . cid . "](" . SCREENSHOTS_DIR . "/" . cid . "_portal.png)`n`n")

            md.Write("**Gallery View:**`n")
            md.Write("![Gallery View " . cid . "](" . SCREENSHOTS_DIR . "/" . cid . "_gallery.png)`n`n")

            if (!seenContracts.HasKey(cid)) {
                seenContracts[cid] := true
                contractIds.Push(cid)
            }
        }
        md.Write("---`n`n")
    } else {
        md.Write("> No confirmed transparency links found.`n`n")
        md.Write("---`n`n")
    }
}

md.Close()

if (TAKE_SCREENSHOTS) {
    FileCreateDir, %SCREENSHOTS_DIR%
    contractsTotal := contractIds.MaxIndex() ? contractIds.MaxIndex() : 0
    contractLimit := LimitCount(contractsTotal, MAX_CONTRACTS)
    if (contractLimit > 0) {
        WriteContractList(CONTRACT_LIST_FILE, contractIds, contractLimit)
        CaptureContracts(contractIds, contractLimit)
    }
}

MsgBox, 64, Done, % "Generated " OUTPUT_MD " (projects: " projectLimit ").`nScreenshots dir: " SCREENSHOTS_DIR "."
ExitApp

; -------------------------
; Automation / helpers
; -------------------------

CaptureContracts(contractIds, contractLimit) {
    global SCREENSHOTS_DIR
    global PAGE_LOAD_SLEEP_MS, GALLERY_LOAD_SLEEP_MS
    global GALLERY_CLICK_X, GALLERY_CLICK_Y, GALLERY_SCROLL_WHEELDOWN
    global RESTART_BROWSER_EVERY

    processedSinceRestart := 0
    LaunchEdge()

    Loop, % contractLimit {
        cid := contractIds[A_Index]
        portalPath := SCREENSHOTS_DIR . "\" . cid . "_portal.png"
        galleryPath := SCREENSHOTS_DIR . "\" . cid . "_gallery.png"

        if (FileExist(portalPath) && FileExist(galleryPath)) {
            continue
        }

        url := "https://transparency.dpwh.gov.ph/?project=" . cid

        Send, ^l
        Sleep, 100
        SendRaw, %url%
        Sleep, 100
        Send, {Enter}
        Sleep, %PAGE_LOAD_SLEEP_MS%

        ; Portal screenshot at top
        Send, {Home}
        Sleep, 500
        CaptureActiveWindowPng(portalPath)

        ; Switch to Gallery, then scroll down before screenshot
        ActivateGalleryTab()
        
        ; Scroll down to ensure all images are loaded/visible
        ; User request: "scroll down to see all the images before taking a screenshot"
        Loop, 5 {
            Send, {PgDn}
            Sleep, 300
        }
        Send, {End}
        Sleep, 500
        
        CaptureActiveWindowPng(galleryPath)

        processedSinceRestart := processedSinceRestart + 1
        if (RESTART_BROWSER_EVERY > 0 && processedSinceRestart >= RESTART_BROWSER_EVERY) {
            Process, Close, msedge.exe
            Sleep, 2000
            LaunchEdge()
            processedSinceRestart := 0
        }
    }

    Process, Close, msedge.exe
}

LaunchEdge() {
    Run, msedge.exe --new-window "about:blank"
    WinWait, ahk_exe msedge.exe, , 15
    WinActivate, ahk_exe msedge.exe
    WinWaitActive, ahk_exe msedge.exe, , 15
    WinMaximize, ahk_exe msedge.exe
    Sleep, 1000
}

ActivateGalleryTab() {
    global GALLERY_CLICK_X, GALLERY_CLICK_Y, GALLERY_LOAD_SLEEP_MS
    global GALLERY_FALLBACK_TAB_COUNT
    global GALLERY_USE_TAB_FALLBACK

    ; Attempt 1: click the Gallery tab (window-relative coords)
    Send, {Home}
    Sleep, 250
    Click, %GALLERY_CLICK_X%, %GALLERY_CLICK_Y%
    Sleep, %GALLERY_LOAD_SLEEP_MS%

    ; Attempt 2 (fallback): keyboard navigate to Gallery like the SEC script style
    if (GALLERY_USE_TAB_FALLBACK && GALLERY_FALLBACK_TAB_COUNT > 0) {
        Click, 5, 5
        Sleep, 150
        Loop, %GALLERY_FALLBACK_TAB_COUNT% {
            Send, {Tab}
            Sleep, 40
        }
        Send, {Enter}
        Sleep, %GALLERY_LOAD_SLEEP_MS%
    }
}

CaptureActiveWindowPng(outPath) {
    WinGetPos, x, y, w, h, A
    if (w = "" || h = "" || w <= 0 || h <= 0) {
        return false
    }
    psOutPath := StrReplace(outPath, "'", "''")

    ps := "Add-Type -AssemblyName System.Drawing; "
        . "$x=" . x . "; $y=" . y . "; $w=" . w . "; $h=" . h . "; "
        . "$bmp = New-Object System.Drawing.Bitmap $w, $h; "
        . "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        . "$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size); "
        . "$bmp.Save('" . psOutPath . "', [System.Drawing.Imaging.ImageFormat]::Png); "
        . "$g.Dispose(); $bmp.Dispose();"

    RunWait, powershell -NoProfile -ExecutionPolicy Bypass -Command "%ps%",, Hide
    return FileExist(outPath)
}

WriteContractList(outFile, contractIds, contractLimit) {
    f := FileOpen(outFile, "w", "UTF-8")
    if (!IsObject(f)) {
        return false
    }
    Loop, % contractLimit {
        f.WriteLine(contractIds[A_Index])
    }
    f.Close()
    return true
}

LimitCount(total, max) {
    if (max <= 0)
        return total
    return (total > max) ? max : total
}

NowTimestamp() {
    FormatTime, ts,, yyyy-MM-dd HH:mm:ss
    return ts
}

FormatCurrency(amount) {
    try {
        v := amount + 0
        return "₱" . Format("{:,.2f}", v)
    } catch e {
        return "" . amount
    }
}

JsonParse(jsonText) {
    doc := ComObjCreate("htmlfile")
    doc.write("<meta http-equiv='X-UA-Compatible' content='IE=9'>")
    return doc.parentWindow.JSON.parse(jsonText)
}

JsArrayAt(arr, idx) {
    try {
        return arr[idx]
    } catch e {
        return arr.item(idx)
    }
}

LoadConfig() {
    global INI_FILE
    global PAGE_LOAD_SLEEP_MS, GALLERY_LOAD_SLEEP_MS
    global GALLERY_CLICK_X, GALLERY_CLICK_Y, GALLERY_SCROLL_WHEELDOWN
    global GALLERY_FALLBACK_TAB_COUNT, GALLERY_USE_TAB_FALLBACK
    global RESTART_BROWSER_EVERY

    IniRead, v, %INI_FILE%, timing, page_load_sleep_ms, %PAGE_LOAD_SLEEP_MS%
    PAGE_LOAD_SLEEP_MS := v
    IniRead, v, %INI_FILE%, timing, gallery_load_sleep_ms, %GALLERY_LOAD_SLEEP_MS%
    GALLERY_LOAD_SLEEP_MS := v

    IniRead, v, %INI_FILE%, coords, gallery_x, %GALLERY_CLICK_X%
    GALLERY_CLICK_X := v
    IniRead, v, %INI_FILE%, coords, gallery_y, %GALLERY_CLICK_Y%
    GALLERY_CLICK_Y := v

    IniRead, v, %INI_FILE%, behavior, gallery_scroll_wheeldown, %GALLERY_SCROLL_WHEELDOWN%
    GALLERY_SCROLL_WHEELDOWN := v
    IniRead, v, %INI_FILE%, behavior, gallery_fallback_tab_count, %GALLERY_FALLBACK_TAB_COUNT%
    GALLERY_FALLBACK_TAB_COUNT := v
    IniRead, v, %INI_FILE%, behavior, gallery_use_tab_fallback, %GALLERY_USE_TAB_FALLBACK%
    GALLERY_USE_TAB_FALLBACK := v
    IniRead, v, %INI_FILE%, behavior, restart_browser_every, %RESTART_BROWSER_EVERY%
    RESTART_BROWSER_EVERY := v
}

ShowConfig() {
    global INI_FILE
    global PAGE_LOAD_SLEEP_MS, GALLERY_LOAD_SLEEP_MS
    global GALLERY_CLICK_X, GALLERY_CLICK_Y, GALLERY_SCROLL_WHEELDOWN
    global GALLERY_FALLBACK_TAB_COUNT, GALLERY_USE_TAB_FALLBACK
    global RESTART_BROWSER_EVERY

    MsgBox, 64, generate_report.ahk config,
    (LTrim Join`n
        INI: %INI_FILE%

        GALLERY_CLICK_X/Y: %GALLERY_CLICK_X% / %GALLERY_CLICK_Y% (window-relative)
        GALLERY_SCROLL_WHEELDOWN: %GALLERY_SCROLL_WHEELDOWN%
        GALLERY_USE_TAB_FALLBACK: %GALLERY_USE_TAB_FALLBACK%
        GALLERY_FALLBACK_TAB_COUNT: %GALLERY_FALLBACK_TAB_COUNT%

        PAGE_LOAD_SLEEP_MS: %PAGE_LOAD_SLEEP_MS%
        GALLERY_LOAD_SLEEP_MS: %GALLERY_LOAD_SLEEP_MS%
        RESTART_BROWSER_EVERY: %RESTART_BROWSER_EVERY%

        Hotkeys:
        - F1 show config
        - F2 set Gallery click coords (hover Gallery tab in Edge)
    )
}

CaptureGalleryCoords() {
    global INI_FILE
    global GALLERY_CLICK_X, GALLERY_CLICK_Y

    MouseGetPos, mx, my
    GALLERY_CLICK_X := mx
    GALLERY_CLICK_Y := my
    IniWrite, %mx%, %INI_FILE%, coords, gallery_x
    IniWrite, %my%, %INI_FILE%, coords, gallery_y
    ToolTip, Saved Gallery click coords: %mx%, %my%
    SetTimer, ClearToolTip, -1200
}

ClearToolTip:
ToolTip
return

F1::
ShowConfig()
return

F2::
CaptureGalleryCoords()
return

