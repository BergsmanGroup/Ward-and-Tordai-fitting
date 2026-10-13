Attribute VB_Name = "ChkForms"
'This module contains the functions and subroutines that check the users
'input for errors.

Public ErrMessage As String

Function chkMain() As Boolean

Dim chkError As Boolean, _
    chkSave As Boolean, _
    myError As Object, _
    chkValue As Boolean

chkError = False
chkSave = False

With frmMain
    For i = 0 To 15
        'Items to check are placed in the case selection
        Select Case i
            Case 0 'Check Adsorption Time
                ErrMessage = "Adsorption time"
                Set myError = .txtAdTime
                chkValue = True
            Case 1 'Check Bulk Concentration
                ErrMessage = "Bulk concentration"
                Set myError = .txtBulkConc
                chkValue = True
            Case 2 'Check Diffusivity
                ErrMessage = "Diffusivity"
                Set myError = .txtDiffusion
                chkValue = True
            Case 3 'Check Solvent Surface Tension
                ErrMessage = "Solvent surface tension"
                Set myError = .txtSolTen
                chkValue = False
            Case 4 'Check Temperature
                ErrMessage = "Temperature"
                Set myError = .txtTemp
                chkValue = False
            Case 5 'Check Activiation Barrier
                ErrMessage = "Activation barrier"
                Set myError = .txtCMC
                chkValue = True
            Case 6 'Check Bubble Radius
                ErrMessage = "Bubble radius"
                Set myError = .txtBubRad
                chkValue = False
            Case 7 'Check Isotherm Parameter A
                ErrMessage = "Isotherm parameter a"
                Set myError = .txtIsoParaA
                chkValue = True
            Case 8 'Check Isotherm Parameter B
                ErrMessage = "Isotherm parameter b"
                Set myError = .txtIsoParaB
                chkValue = True
            Case 9 'Check Isotherm Parameter C
                ErrMessage = "Isotherm parameter c"
                Set myError = .txtIsoParaC
                chkValue = False
            Case 10 'Check Time Steps
                ErrMessage = "Number of time steps"
                Set myError = .txtNumSteps
                chkValue = True
            Case 11 'Check Minimum Time Step
                ErrMessage = "Minimum time step"
                Set myError = .txtMinStep
                chkValue = True
            Case 12 'Check Solution Tolerance
                ErrMessage = "Solution tolerance"
                Set myError = .txtSolTol
                chkValue = True
            Case 13 'Check Next Root Tolerance
                ErrMessage = "Next root tolerance"
                Set myError = .txtRootTol
                chkValue = True
            Case 14 'Check Initial Tweak
                ErrMessage = "Initial tweak"
                Set myError = .txtInitTweak
                chkValue = True
            Case 15 'Check Successive Tweaks
                ErrMessage = "Succesive tweaks"
                Set myError = .txtSucTweaks
                chkValue = True
        End Select
        chkError = chkPar(myError, ErrMessage, chkValue)
        If chkError Then
            frmError.lstError.AddItem (ErrMessage)
            chkSave = True
        End If
    Next i
End With

'Tell main program if errors were found!
chkMain = chkSave

End Function


Function chkPar(chkBox As Object, _
                 chkMessage As String, _
                 chkSign As Boolean) As Boolean
                 
                 
'All numbers must be numbers
If (Not IsNumeric(chkBox)) Then
    chkPar = True
    ErrMessage = ErrMessage & " is not numeric"
    Exit Function
End If

'All numbers must generally be positive
If (chkSign And chkBox <= 0) Then
    chkPar = True
    ErrMessage = ErrMessage & " is negative"
    Exit Function
End If

chkPar = False

End Function
