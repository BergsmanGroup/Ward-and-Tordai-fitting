VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "Sheet2"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True

Private Sub chkPlotSave1_Change()

Dim PlotD As Boolean, _
    PlotS As Integer, _
    PlotWS As Worksheet

PlotD = Sheet2.chkPlotSave1.Value
PlotS = 2
Set PlotWS = Sheet4

PlotData PlotBool:=PlotD, PlotSeries:=PlotS, PlotSheet:=PlotWS

End Sub

Private Sub chkPlotSave2_Change()

Dim PlotD As Boolean, _
    PlotS As Integer, _
    PlotWS As Worksheet

PlotD = Sheet2.chkPlotSave2.Value
PlotS = 3
Set PlotWS = Sheet5

PlotData PlotBool:=PlotD, PlotSeries:=PlotS, PlotSheet:=PlotWS

End Sub

Private Sub chkPlotSave3_Change()

Dim PlotD As Boolean, _
    PlotS As Integer, _
    PlotWS As Worksheet

PlotD = Sheet2.chkPlotSave3.Value
PlotS = 4
Set PlotWS = Sheet6

PlotData PlotBool:=PlotD, PlotSeries:=PlotS, PlotSheet:=PlotWS

End Sub

Private Sub chkPlotSave4_Change()

Dim PlotD As Boolean, _
    PlotS As Integer, _
    PlotWS As Worksheet

PlotD = Sheet2.chkPlotSave4.Value
PlotS = 5
Set PlotWS = Sheet7

PlotData PlotBool:=PlotD, PlotSeries:=PlotS, PlotSheet:=PlotWS

End Sub

Private Sub cmdReplot_Click()

'Declare chart variable
Dim XMin As Double, _
    XMax As Double, _
    XInt As Double, _
    XLog As Boolean, _
    YMin As Double, _
    YMax As Double, _
    YInt As Double, _
    YLog As Boolean, _
    SubErrors As Boolean, _
    ErrorMessage As String

'Simplify chart references
Set ZChart = Sheet2.ChartObjects(1)

'Read chart variables
With Sheet2
    XMin = Val(.txtXmin.Value)
    XMax = Val(.txtXmax.Value)
    XInt = Val(.txtXint.Value)
    XLog = .chkXlog.Value
    YMin = Val(.txtYmin.Value)
    YMax = Val(.txtYMax.Value)
    YInt = Val(.txtYint.Value)
    YLog = .chkYlog.Value
End With

'A quick scan for common user mistakes
SubErrors = False
frmError.lstError.Clear
If ((XInt <= 0) Or (YInt <= 0)) Then
    ErrorMessage = "Interval less than or equal to zero!"
    frmError.lstError.AddItem (ErrorMessage)
    SubErrors = True
End If
If (XLog) Then
    If ((XMin = 0) Or (XMax = 0)) Then
        ErrorMessage = "x-axis zeros are not permitted in log scale."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    ElseIf ((Log(XMin) / Log(10)) - AbbInt(Log(XMin) / Log(10)) > 0.0000000001) Then
        ErrorMessage = "x-axis minimum is not a multiple of 10."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    ElseIf ((Log(XMax) / Log(10)) - AbbInt(Log(XMax) / Log(10)) > 0.0000000001) Then
        ErrorMessage = "x-axis maximum is not a multiple of 10."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
        BlehA = ((Log(XMax) / Log(10)) - AbbInt(Log(XMax) / Log(10)))
        Stop
    ElseIf (XInt < 10 Or ((Log(XInt) / Log(10)) - AbbInt(Log(XInt) / Log(10)) > 0.0000000001)) Then
        ErrorMessage = "x-axis interval is invalid."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    End If
End If
If (YLog) Then
    If ((YMin = 0) Or (YMax = 0)) Then
        ErrorMessage = "y-axis zeros are not permitted in log scale."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    ElseIf ((Log(YMin) / Log(10)) - AbbInt(Log(YMin) / Log(10)) > 0.0000000001) Then
        ErrorMessage = "y-axis minimum is not a multiple of 10."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    ElseIf ((Log(YMax) / Log(10)) - AbbInt(Log(YMax) / Log(10)) > 0.0000000001) Then
        ErrorMessage = "y-axis maximum is not a multiple of 10."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    ElseIf (YInt < 10 Or ((Log(YInt) / Log(10)) - AbbInt(Log(YInt) / Log(10)) > 0.0000000001)) Then
        ErrorMessage = "y-axis interval is invalid."
        frmError.lstError.AddItem (ErrorMessage)
        SubErrors = True
    End If
End If


'Activate and apply changes to chart

If (SubErrors) Then
    frmError.Show
Else
    ZChart.Activate
    With ActiveChart.Axes(xlCategory) 'Apply x-axis changes
        If (XLog And (Not .ScaleType = -4133)) Then
            If (Not .MinimumScale = XMin) Then .MinimumScale = XMin
            If (Not .MaximumScale = XMax) Then .MaximumScale = XMax
            If (Not .MajorUnit = XInt) Then .MajorUnit = XInt
            .ScaleType = xlLogarithmic
        ElseIf (Not XLog And (Not .ScaleType = -4132)) Then
            .ScaleType = xlLinear
            If (Not .MinimumScale = XMin) Then .MinimumScale = XMin
            If (Not .MaximumScale = XMax) Then .MaximumScale = XMax
            If (Not .MajorUnit = XInt) Then .MajorUnit = XInt
        Else
            If (Not .MinimumScale = XMin) Then .MinimumScale = XMin
            If (Not .MaximumScale = XMax) Then .MaximumScale = XMax
            If (Not .MajorUnit = XInt) Then .MajorUnit = XInt
        End If
    End With

    With ActiveChart.Axes(xlValue) 'Apply y-axis changes
        If (YLog And (Not .ScaleType = -4133)) Then
            If (Not .MinimumScale = YMin) Then .MinimumScale = YMin
            If (Not .MaximumScale = YMax) Then .MaximumScale = YMax
            If (Not .MajorUnit = YInt) Then .MajorUnit = YInt
            .ScaleType = xlLogarithmic
        ElseIf (Not YLog And (Not .ScaleType = -4132)) Then
            .ScaleType = xlLinear
            If (Not .MinimumScale = YMin) Then .MinimumScale = YMin
            If (Not .MaximumScale = YMax) Then .MaximumScale = YMax
            If (Not .MajorUnit = YInt) Then .MajorUnit = YInt
        Else
            If (Not .MinimumScale = YMin) Then .MinimumScale = YMin
            If (Not .MaximumScale = YMax) Then .MaximumScale = YMax
            If (Not .MajorUnit = YInt) Then .MajorUnit = YInt
        End If
    End With
              
End If

End Sub

Sub PlotData(PlotBool As Boolean, _
             PlotSeries As Integer, _
             PlotSheet As Worksheet)
             
Dim StartCell As Long, _
    EndCell As Long, _
    PlotWhat As Integer
    
'This subroutine removes or adds a plot of the current data
Sheet2.ChartObjects(1).Activate
With PlotSheet
    StartCell = .Cells(3, 2).Value
    EndCell = .Cells(4, 2).Value
    PlotWhat = Sheet2.ComboPlot.ListIndex + 2
    If PlotBool Then 'Add current data points
        ActiveChart.SeriesCollection(PlotSeries).XValues = .Range(.Cells(StartCell, 1), .Cells(EndCell, 1))
        ActiveChart.SeriesCollection(PlotSeries).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
    Else 'Remove current data points
        ActiveChart.SeriesCollection(PlotSeries).XValues = .Cells(3, 3)
        ActiveChart.SeriesCollection(PlotSeries).Values = .Cells(4, 3)
    End If
End With

Sheet2.Cells(16, 10).Select

End Sub

Function AbbInt(AbbX As Double) As Double

Dim AbbA As Double, _
    AbbB As Double

AbbA = AbbX - Int(AbbX)
AbbB = 0
If AbbA > 0.5 Then AbbB = 1
AbbInt = Int(AbbX) + AbbB

End Function

Private Sub cmdSaveData_Click()

Dim SlotNum As Integer, _
    DestSheet As Worksheet, _
    R As Double
    
R = 83145000

Select Case Sheet2.ComboSave.ListIndex
    Case 0 'save data to slot 1
        Set DestSheet = Sheet4
    Case 1 'save data to slot 2
        Set DestSheet = Sheet5
    Case 2 'save data to slot 3
        Set DestSheet = Sheet6
    Case 3 'save data to slot 4
        Set DestSheet = Sheet7
End Select

With DestSheet
    .Cells(3, 2) = 35
    .Cells(4, 2) = Sheet3.Cells(34, 2) + 33
    
    .Cells(5, 2) = trun
    .Cells(6, 2) = C(0)
    .Cells(7, 2) = D
    .Cells(8, 2) = frmMain.txtSolTen
    .Cells(9, 2) = RT / R - 273.15
    
    For i = 10 To 13
        .Cells(i, 2) = Sheet3.Cells(i, 2)
    Next i
    
    .Cells(14, 2) = Sheet3.Cells(17, 2)
    .Cells(15, 2) = aL
    .Cells(16, 2) = Ginf
    .Cells(17, 2) = kL
    .Cells(18, 2) = pL
    
    For i = 19 To 21
        .Cells(i, 2) = Sheet3.Cells(i + 15, 2)
    Next i

    For i = 22 To 26
        .Cells(i, 2) = Sheet3.Cells(i + 18, 2)
    Next i

    For i = 28 To 29
        .Cells(i, 2) = Sheet2.Cells(i + 3, 2)
    Next i
    
    For i = 34 To (Sheet3.Cells(34, 2) + 33)
        .Cells(i, 1) = Sheet2.Cells(i + 5, 1)
        .Cells(i, 2) = Sheet2.Cells(i + 5, 2)
        .Cells(i, 3) = Sheet2.Cells(i + 5, 3)
        .Cells(i, 4) = Sheet2.Cells(i + 5, 4)
    Next i
    
'    For i = 5 To 13
'        .Cells(i, 2) = Sheet3.Cells(i, 2)
'    Next i
'
'    .Cells(14, 2) = Sheet3.Cells(17, 2)
'
'    For i = 15 To 18
'        .Cells(i, 2) = Sheet3.Cells(i + 12, 2)
'    Next i
'
'    For i = 19 To 21
'        .Cells(i, 2) = Sheet3.Cells(i + 15, 2)
'    Next i
'
'    For i = 22 To 26
'        .Cells(i, 2) = Sheet3.Cells(i + 18, 2)
'    Next i
'
'    For i = 28 To 29
'        .Cells(i, 2) = Sheet2.Cells(i + 3, 2)
'    Next i
'
'    For i = 34 To (Sheet3.Cells(34, 2) + 33)
'        .Cells(i, 1) = Sheet2.Cells(i + 5, 1)
'        .Cells(i, 2) = Sheet2.Cells(i + 5, 2)
'        .Cells(i, 3) = Sheet2.Cells(i + 5, 3)
'        .Cells(i, 4) = Sheet2.Cells(i + 5, 4)
'    Next i
End With

End Sub

Private Sub ComboPlot_Change()

Dim PlotWhat As Integer, _
    PlotSeries As Integer, _
    Type1 As String, _
    Type2 As String, _
    Type3 As String

PlotWhat = Sheet2.ComboPlot.ListIndex + 2
Type1 = Cells(3, 2)
Type2 = Cells(4, 2)
Type3 = Cells(5, 2)
Sheet2.ChartObjects(1).Activate
With Sheet2
    'Replot current data
    StartCell = 40
    EndCell = Sheet3.Cells(34, 2) + 38
    ActiveChart.SeriesCollection(1).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
End With

'Replot Save 1
If Sheet2.chkPlotSave1 Then
    With Sheet4
        StartCell = .Cells(3, 2).Value
        EndCell = .Cells(4, 2).Value
        ActiveChart.SeriesCollection(2).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
    End With
End If

'Replot Save 2
If Sheet2.chkPlotSave2 Then
    With Sheet5
        StartCell = .Cells(3, 2).Value
        EndCell = .Cells(4, 2).Value
        ActiveChart.SeriesCollection(3).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
    End With
End If

'Replot Save 3
If Sheet2.chkPlotSave3 Then
    With Sheet6
        StartCell = .Cells(3, 2).Value
        EndCell = .Cells(4, 2).Value
        ActiveChart.SeriesCollection(4).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
    End With
End If

'Replot Save 4
If Sheet2.chkPlotSave4 Then
    With Sheet7
        StartCell = .Cells(3, 2).Value
        EndCell = .Cells(4, 2).Value
        ActiveChart.SeriesCollection(5).Values = .Range(.Cells(StartCell, PlotWhat), .Cells(EndCell, PlotWhat))
    End With
End If

    With ActiveChart.Axes(xlValue, xlPrimary)
        Select Case PlotWhat
            Case 2 'Surface Tension
            .AxisTitle.Text = Type1
            Case 3 'Surface Concentration
            .AxisTitle.Text = Type2
            Case 4 'Subsurface Concentration
            .AxisTitle.Text = Type3
        End Select
    End With

Sheet2.Cells(16, 10).Select

End Sub
