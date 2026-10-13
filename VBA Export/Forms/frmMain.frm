VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmMain 
   Caption         =   "Adsorb v1.0"
   ClientHeight    =   6705
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   9540.001
   OleObjectBlob   =   "frmMain.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "frmMain"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit


Private Sub CheckBox5_Change()

'This will diable some options when save data is applied.
chkAllowedOptions

End Sub


Private Sub CheckBox4_Change()

'This will disable some options when next root estimation is applied.
chkAllowedOptions

End Sub


Private Sub CheckBox3_Change()

'This will disable some options when next root estimation is applied.
chkAllowedOptions

End Sub


Private Sub CheckBox1_Change()

'This will disable some options when mixed-kinetic control is applied.
chkAllowedOptions

End Sub


Private Sub CheckBox2_Change()

'This will disable some options when interfacial curvature is applied.
chkAllowedOptions

End Sub


Private Sub chkIsoParamOpt_Click()

'This will disable or enable the optimization of the isotherm parameters
chkAllowedOptions

End Sub

Private Sub cmdRunCalc_Click()

Dim mySheet As Worksheet, _
    RunTimeError As Boolean

'Checks for errors, then saves the input parameters and runs the program.
svParameters
RunTimeError = chkMain
If RunTimeError Then
    frmError.Show
Else
    Select Case frmMain.ComboBox2.ListIndex
        Case 0
            Set mySheet = Sheet2
        Case 1
            Set mySheet = Sheet3
        Case 2
            Set mySheet = Sheet4
        Case 3
            Set mySheet = Sheet5
        Case 4
            Set mySheet = Sheet6
        Case 5
            Set mySheet = Sheet7
    End Select
    frmMain.Hide
    Main
    mySheet.Activate
End If

End Sub


Private Sub cmdSaveClose_Click()

Dim RunTimeError As Boolean

'Saves the input and hides the user form.
svParameters
RunTimeError = chkMain
If RunTimeError Then
    frmError.Show
Else
    frmMain.Hide
End If

End Sub

Private Sub cmdDiscardClose_Click()

'Closes the frmMain without saving changes made by the user.
frmMain.Hide

End Sub

Private Sub lstIsoTypes_Change()

'This will change the isotherm display when the user changes the format
'of the isotherm.  The appropriate isotherm parameters are then made
'available to the user.


Dim IsoType As Integer, _
    WorkingDirectory As String

WorkingDirectory = ReturnDirectory()
With frmMain
    IsoType = .lstIsoTypes.ListIndex + 1
    Select Case IsoType
        Case 1
            .imgIsoType.Picture = LoadPicture(WorkingDirectory & "pictures\henry.gif")
        Case 2
            .imgIsoType.Picture = LoadPicture(WorkingDirectory & "pictures\langmuir.gif")
        Case 3
            .imgIsoType.Picture = LoadPicture(WorkingDirectory & "pictures\frumkin.gif")
        Case 4
            .imgIsoType.Picture = LoadPicture(WorkingDirectory & "pictures\gen-frumkin.gif")
    End Select
End With
chkAllowedOptions

End Sub


Private Sub UserForm_Activate()

'Initializes the data fields whenever the form is activated!
InitDataFields
chkAllowedOptions

End Sub


Private Sub UserForm_Initialize()

'Initialize list and combobox contents.
With frmMain
    With lstIsoTypes
        .AddItem ("Henry")
        .AddItem ("Langmuir")
        .AddItem ("Frumkin")
        .AddItem ("Gen-Frumkin")
        .ListIndex = 0
    End With

    With ComboBox2
        .AddItem ("Console")
        .AddItem ("Console Save")
        .AddItem ("Slot 1")
        .AddItem ("Slot 2")
        .AddItem ("Slot 3")
        .AddItem ("Slot 4")
        .ListIndex = 0
    End With
End With

End Sub
