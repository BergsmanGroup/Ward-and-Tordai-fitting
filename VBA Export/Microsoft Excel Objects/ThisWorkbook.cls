VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ThisWorkbook"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True
Private Sub Workbook_Open()

Dim iter As Integer, _
    slotstr As String

With Sheet2
    For iter = 1 To 4
    slotstr = "Slot " & iter
        .ComboSave.AddItem (slotstr)
        '.ComboClear.AddItem (slotstr)
    Next iter
    .ComboSave.ListIndex = 0
    '.ComboClear.ListIndex = 0
End With

With Sheet2.ComboPlot
    .AddItem ("Surface Tension")
    .AddItem ("Surface Concentration")
    .AddItem ("Subsurface Concentration")
    .ListIndex = 0
End With

End Sub

