Attribute VB_Name = "ModMain"
'This is the main program module.  While it does contain a few important
'subroutines (e.g., TimeVector), it mainly just calls the other routines
'needed to solve the Ward and Tordai equation.  It's focus is to initialize
'the program variables and post the results.

Public trun As Double, _
       D As Double, _
       so As Double, _
       RT As Double, _
       boolkmic As Boolean, _
       kmic As Double, _
       boolB As Boolean, _
       B As Double, _
       aL As Double, _
       Ginf As Double, _
       kL As Double, _
       pL As Double, _
       NTot As Integer, _
       tmin As Double, _
       Tol As Double, _
       boolRootEst As Boolean, _
       RootEstTol As Double, _
       boolSolTweak As Boolean, _
       InitSolTweak As Double, _
       SucSolTweak As Double, _
       Pi As Double, _
       G(1000) As Double, _
       C(1000) As Double, _
       s(1000) As Double, _
       t(1000) As Double
       
Public Temp As Double, _
    Cb As Double



Sub Main()

'This subroutine simply acts as a focus for call all subsequent subroutines.

ParameterRead
TimeVector
Equilibrium
NumericSolution 'This is not contained in this module...
ParameterOptimization 'This is also not contained in this module...
ResultsPost

End Sub


Sub ParameterRead()

'This section of code reads all the user input variables.

Dim R As Double

Sheet2.Cells(26, 2) = "Reading program parameters..."

With frmMain
    trun = .txtAdTime                                       'total time of adsorption (s)
    Cb = .txtBulkConc                                       'bulk concentration of surfactant (mol/cm³)
    C(0) = Cb
    D = .txtDiffusion                                       'surfactant diffusion coefficient (cm²/s)
    so = .txtSolTen                                         'solvent surface tension (dyne/cm)
    Temp = .txtTemp + 273.15                                'absolute temperature (K)

    boolkmic = .CheckBox1                                   'post-CMC calculations on/off
    kmic = .txtCMC                                          'activation barrier (ergs/mol)
    boolB = .CheckBox2                                      'curvature on/off
    B = .txtBubRad                                          'bubble radius of curvature (cm)

    aL = .txtIsoParaA                                       'surface reactivity (mol/cm³)
    Ginf = .txtIsoParaB                                     'monolayer capacity(mol/cm²)
    kL = .txtIsoParaC                                       'surface interaction parameter
    pL = .txtIsoParaD                                       'surface interaction power law

    NTot = .txtNumSteps                                     'total number of time steps
    tmin = .txtMinStep                                      'sets the value of the minimum time step
    Tol = .txtSolTol * Ginf                                 'solution tolerance (mol/cm²)
    
    boolRootEst = .CheckBox3                                'root estimating on/off
    RootEstTol = .txtRootTol                                'tolerance for next root estimating
    
    boolSolTweak = .CheckBox4                               'root tweaking on/off
    InitSolTweak = .txtInitTweak                            'initial root tweak
    SucSolTweak = .txtSucTweaks                             'sucessive tweaking
End With

R = 83145000#
RT = R * Temp
Pi = 3.14159265358979

End Sub

Sub TimeVector()

'This section of code sets up the time vector for the numerical routine that follows.

Dim AF As Double

Sheet2.Cells(26, 2) = "Setting up numerical routine..."

t(1) = 0
AF = (Log(trun) - Log(tmin)) / (NTot - 1)
For i = 2 To NTot
    t(i) = Exp(AF * (i - NTot) + Log(trun))
Next i

End Sub

Sub Equilibrium()

'This section of code determines the equilibrium adsorption characteristics

Dim IsoTypeVal As Integer

Sheet2.Cells(26, 2) = "Solving equilibrium conditions..."

IsoTypeVal = frmMain.lstIsoTypes.ListIndex + 1
G(0) = AdIso(C(0), 1, IsoTypeVal)
s(0) = SurfTen(G(0), IsoTypeVal)

End Sub

Sub ResultsPost()

Dim R123 As Double

'This results clears old results and prints new data to the console.

With Sheet2
    .Range(.Cells(31, 2), .Cells(32, 2)).Clear
    .Range(.Cells(38, 1), .Cells(1080, 6)).Clear
    
    .Cells(31, 2) = G(0)
    .Cells(32, 2) = s(0)

    For i = 1 To NTot
        'Post Ward and Tordai Results
        .Cells(i + 38, 1).Value = t(i)
        .Cells(i + 38, 2).Value = s(i)
        .Cells(i + 38, 3).Value = G(i)
        .Cells(i + 38, 4).Value = C(i)
        
        'Post Short-Time Limit
        R123 = so - 2 * RT * C(0) * ((D * t(i) / Pi) ^ (0.5))
        If (R123 > s(0)) Then .Cells(i + 38, 5).Value = R123
        
        'Post Long-Time Limit
        If (i = 1) Then R123 = 0
        If (i > 1) Then R123 = s(0) + (RT * (G(0) ^ 2) / C(0)) * ((1 / (Pi * D * t(i))) ^ (0.5))
        If (R123 < so) Then .Cells(i + 38, 6).Value = R123
    Next i
End With

Sheet2.Cells(26, 2) = "Program calculations complete!"

End Sub
