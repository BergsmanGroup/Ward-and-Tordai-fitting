Attribute VB_Name = "InitForms"
'This module contains mostly subroutines that effect the behavior
'and the user forms called by Excel.

Option Explicit


Sub CallUserForm()

'Opens the main user form!
frmMain.Show

End Sub


Sub InitDataFields()
'Initializes / Calls the console save data into the user form!

Dim mySheet As Worksheet, _
    IsoType As Integer, _
    WorkingDirectory As String

WorkingDirectory = ReturnDirectory()

Set mySheet = Sheet3
With frmMain
    .txtAdTime = mySheet.Cells(5, 2)
    .txtBulkConc = mySheet.Cells(6, 2)
    .txtDiffusion = mySheet.Cells(7, 2)
    .txtSolTen = mySheet.Cells(8, 2)
    .txtTemp = mySheet.Cells(9, 2)
    
    .CheckBox1 = mySheet.Cells(10, 2)
    .txtCMC = mySheet.Cells(11, 2)
    .CheckBox2 = mySheet.Cells(12, 2)
    .txtBubRad = mySheet.Cells(13, 2)
    
    .txtIsoParaA = mySheet.Cells(27, 2)
    .txtIsoParaB = mySheet.Cells(28, 2)
    .txtIsoParaC = mySheet.Cells(29, 2)
    .txtIsoParaD = mySheet.Cells(30, 2)
    
    .txtNumSteps = mySheet.Cells(34, 2)
    .txtMinStep = mySheet.Cells(35, 2)
    .txtSolTol = mySheet.Cells(36, 2)
    
    .CheckBox3 = mySheet.Cells(40, 2)
    .txtRootTol = mySheet.Cells(41, 2)
    .CheckBox4 = mySheet.Cells(42, 2)
    .txtInitTweak = mySheet.Cells(43, 2)
    .txtSucTweaks = mySheet.Cells(44, 2)
    
    .chkVaryIsoA = mySheet.Cells(48, 2)
    .chkVaryIsoB = mySheet.Cells(49, 2)
    .chkVaryIsoC = mySheet.Cells(50, 2)
    .chkVaryIsoD = mySheet.Cells(51, 2)
    .chkVaryDiff = mySheet.Cells(52, 2)
    .chkVaryBulkConc = mySheet.Cells(53, 2)
    .chkVaryTemp = mySheet.Cells(54, 2)
    .chkLongTime = mySheet.Cells(59, 2)
    
End With

End Sub


Sub svParameters()

'This subroutine saves the user input parameters
Dim mySheet As Worksheet

Set mySheet = Sheet3
With frmMain
    mySheet.Cells(5, 2) = .txtAdTime
    mySheet.Cells(6, 2) = .txtBulkConc
    mySheet.Cells(7, 2) = .txtDiffusion
    mySheet.Cells(8, 2) = .txtSolTen
    mySheet.Cells(9, 2) = .txtTemp
    
    mySheet.Cells(10, 2) = .CheckBox1
    mySheet.Cells(11, 2) = .txtCMC
    mySheet.Cells(12, 2) = .CheckBox2
    mySheet.Cells(13, 2) = .txtBubRad
    
    mySheet.Cells(17, 2) = .lstIsoTypes.ListIndex
    
    mySheet.Cells(27, 2) = .txtIsoParaA
    mySheet.Cells(28, 2) = .txtIsoParaB
    mySheet.Cells(29, 2) = .txtIsoParaC
    mySheet.Cells(30, 2) = .txtIsoParaD
    
    mySheet.Cells(34, 2) = .txtNumSteps
    mySheet.Cells(35, 2) = .txtMinStep
    mySheet.Cells(36, 2) = .txtSolTol
    
    mySheet.Cells(40, 2) = .CheckBox3
    mySheet.Cells(41, 2) = .txtRootTol
    mySheet.Cells(42, 2) = .CheckBox4
    mySheet.Cells(43, 2) = .txtInitTweak
    mySheet.Cells(44, 2) = .txtSucTweaks
    
    mySheet.Cells(48, 2) = .chkVaryIsoA
    mySheet.Cells(49, 2) = .chkVaryIsoB
    mySheet.Cells(50, 2) = .chkVaryIsoC
    mySheet.Cells(51, 2) = .chkVaryIsoD
    mySheet.Cells(52, 2) = .chkVaryDiff
    mySheet.Cells(53, 2) = .chkVaryBulkConc
    mySheet.Cells(54, 2) = .chkVaryTemp
    mySheet.Cells(59, 2) = .chkLongTime
End With
End Sub


Sub chkAllowedOptions()

'This subroutine determines the program setup the user is allowed to select.
With frmMain

    'Checks the options for a positive CheckBox1
    If .CheckBox1 Then
        .CheckBox2 = False
        .CheckBox2.Enabled = False
        .txtBubRad.Enabled = False
    Else
        .CheckBox2.Enabled = True
        .txtBubRad.Enabled = True
    End If
    
    'Checks the options for a positive CheckBox2
    If .CheckBox2 Then
        .CheckBox1 = False
        .CheckBox1.Enabled = False
        .txtCMC.Enabled = False
    Else
        .CheckBox1.Enabled = True
        .txtCMC.Enabled = True
    End If
    
    'Checks the isotherm arguments and makes the appropriate parameters
    'available.
    Select Case .lstIsoTypes.ListIndex
        Case 0 'Henry
            .txtIsoParaA.Enabled = True
            .txtIsoParaB.Enabled = True
            .txtIsoParaC.Enabled = False
            .txtIsoParaD.Enabled = False
        Case 1 'Langmuir
            .txtIsoParaA.Enabled = True
            .txtIsoParaB.Enabled = True
            .txtIsoParaC.Enabled = False
            .txtIsoParaD.Enabled = False
        Case 2 'Frumkin
            .txtIsoParaA.Enabled = True
            .txtIsoParaB.Enabled = True
            .txtIsoParaC.Enabled = True
            .txtIsoParaD.Enabled = False
        Case 3 'General
            .txtIsoParaA.Enabled = True
            .txtIsoParaB.Enabled = True
            .txtIsoParaC.Enabled = True
            .txtIsoParaD.Enabled = True
    End Select
    
    'Checks if the isotherm parameters are allowed to vary or not
    If .chkIsoParamOpt Then
        .chkVaryIsoA.Enabled = True
        .chkVaryIsoB.Enabled = True
        .chkVaryIsoC.Enabled = True
        .chkVaryIsoD.Enabled = True
    Else
        .chkVaryIsoA.Enabled = False
        .chkVaryIsoB.Enabled = False
        .chkVaryIsoC.Enabled = False
        .chkVaryIsoD.Enabled = False
        .chkVaryIsoA.Value = False
        .chkVaryIsoB.Value = False
        .chkVaryIsoC.Value = False
        .chkVaryIsoD.Value = False
    End If
    
    'Checks if Next Root Estimation is on and enables or disables the
    'text boxes appropriately.
    If .CheckBox3 Then
        .txtRootTol.Enabled = True
    Else
        .txtRootTol.Enabled = False
    End If
    
    'Checks if Root Tweaking is on and enables or disables the
    'appropriate text boxes
    If .CheckBox4 Then
        .txtInitTweak.Enabled = True
        .txtSucTweaks.Enabled = True
    Else
        .txtInitTweak.Enabled = False
        .txtSucTweaks.Enabled = False
    End If
    
End With

End Sub


Function ReturnDirectory() As String

'Determines and returns the current working program directory!
'I hope this is where future users have the picture files!

Dim fs As Object, _
    i As Integer, _
    myStr1 As String, _
    myStr2 As String, _
    CutStr As Long

Set fs = Application.ActiveWorkbook
With fs
    myStr1 = .FullName
    myStr2 = .Name
End With
CutStr = Len(myStr1) - Len(myStr2)
ReturnDirectory = Left(myStr1, CutStr)

End Function
