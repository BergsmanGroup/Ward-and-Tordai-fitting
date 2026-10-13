Attribute VB_Name = "EqAdsorb"
'This Module Calculates the equilibrium properties of a solution with a known
'bulk/surface concentration X.  It contains a function representing the
'adsorption isotherm and another representing the surface equation of state.
'
'Generalized Adsorption Isotherm Module.  Kinds are as follows:
'   1   :   G=G(C)
'   2   :   C=C(G)
'
'It should be noted that the surface tension module will use only surface
'concentrations, and, therefore, only have on Kind associated with them. In
'other words, the Kinds classification applies only to the AdIso module.
'Modes are as follows:
'   1   :   Henry
'   2   :   Langmuir
'   3   :   Frumkin
'   4   :   Generalized Frumkin
'
'When using, the isotherm parameters must be declared global variables in the
'main program routine.  In addition, the isotherm parameters may take only
'the specified variables names below:
'   aL  :   Surface activity parameter (mol/cm³)
'   Ginf:   Monolayer capacity (mol/cm²)
'   kL  :   Surface interaction parameter (dimensionless)
'   pL  :   Generalized frumkin power (dimensionless)
'
'In addition to these parameters, the surface tension module also needs the
'following additional parameters:
'   RT  :   Universal gas constant times the absolute temperature (erg/mol)
'   so  :   Solvent surface tension (dyne/cm)


Function AdIso(x As Double, _
               Optional Kind As Integer = 1, _
               Optional Mode As Integer = 4)
               
Dim Multi As Single, _
    GEst1 As Double, _
    GEst2 As Double, _
    GEst3 As Double, _
    EQG1 As Double, _
    EQG2 As Double, _
    EQG3 As Double, _
    IsoIter As Variant
               
IsoIter = 25
On Error Resume Next
               
Select Case Kind
Case 1  'Treat as a G=G(C) isotherm
    
    Select Case Mode
    Case 1  'Henry G=G(C) isotherm
        AdIso = (Ginf / aL) * x
        Exit Function
    Case 2  'Langmuir G=G(C) isotherm
        AdIso = Ginf * x / (aL + x)
        Exit Function
    Case 3  'Frumkin G=G(C) isotherm
        GEst1 = 0
        GEst2 = 0.999999999999999 * Ginf
        EQG3 = 2E-20
        While (Abs(EQG3) > 1E-20)
            GEst3 = 0.5 * (GEst1 + GEst2)
            EQG1 = aL * Exp(-kL * GEst1 / Ginf) * GEst1 / (Ginf - GEst1) - x
            EQG2 = aL * Exp(-kL * GEst2 / Ginf) * GEst2 / (Ginf - GEst2) - x
            EQG3 = aL * Exp(-kL * GEst3 / Ginf) * GEst3 / (Ginf - GEst3) - x
            If EQG1 * EQG2 > 0 Then Stop
            If EQG1 * EQG3 > 0 Then GEst1 = GEst3
            If EQG2 * EQG3 > 0 Then GEst2 = GEst3
        Wend
        AdIso = GEst3
        Exit Function
'        GEst = Ginf * X / (aL + X)
'        For i = 1 To IsoIter
'            Multi = (i / IsoIter)
'            GEst = Ginf * X / (aL * Exp(-kL * Multi * GEst / Ginf) + X)
'        Next i
'        AdIso = GEst
'        Exit Function
    Case 4  'Generalized Frumkin G=G(C) isotherm
        GEst1 = 0
        GEst2 = 0.999999999999999 * Ginf
        EQG3 = 2E-20
        While (Abs(EQG3) > 1E-20)
            GEst3 = 0.5 * (GEst1 + GEst2)
            EQG1 = aL * Exp(-kL * ((GEst1 / Ginf) ^ pL)) * GEst1 / (Ginf - GEst1) - x
            EQG2 = aL * Exp(-kL * ((GEst2 / Ginf) ^ pL)) * GEst2 / (Ginf - GEst2) - x
            EQG3 = aL * Exp(-kL * ((GEst3 / Ginf) ^ pL)) * GEst3 / (Ginf - GEst3) - x
            If EQG1 * EQG2 > 0 Then Stop
            If EQG1 * EQG3 > 0 Then GEst1 = GEst3
            If EQG2 * EQG3 > 0 Then GEst2 = GEst3
        Wend
        AdIso = GEst3
        Exit Function
        'GEst = Ginf * X / (aL + X)
        'For i = 1 To IsoIter
        '    Multi = (i / IsoIter)
        '    GEst = Ginf * X / (aL * Exp(-kL * Multi * ((GEst / Ginf) ^ pL)) + X)
        'Next i
        'AdIso = GEst
        Exit Function
    End Select
    
Case 2      'Treat as a C=C(G) isotherm
    Select Case Mode
    Case 1  'Henry C=C(G) isotherm
        AdIso = (aL / Ginf) * x
        Exit Function
    Case 2  'Langmuir C=C(G) isotherm
        AdIso = aL * x / (Ginf - x)
        Exit Function
    Case 3  'Frumkin C=C(G) isotherm
        AdIso = aL * Exp(-kL * x / Ginf) * x / (Ginf - x)
        Exit Function
    Case 4  'Generalized Frumkin C=C(G) isotherm
        AdIso = aL * Exp(-kL * ((x / Ginf) ^ pL)) * x / (Ginf - x)
        Exit Function
    End Select
End Select
               
End Function


Function SurfTen(x As Double, _
                 Optional Mode As Integer = 4)

Select Case Mode
Case 1  'Henry C=C(G) isotherm
    SurfTen = so - RT * x
    Exit Function
Case 2  'Langmuir C=C(G) isotherm
    SurfTen = so + RT * Ginf * Log(1 - x / Ginf)
    Exit Function
Case 3  'Frumkin C=C(G) isotherm
    SurfTen = so + RT * Ginf * (Log(1 - x / Ginf) + 0.5 * kL * (x / Ginf) ^ 2)
    Exit Function
Case 4  'Generalized Frumkin C=C(G) isotherm
    SurfTen = so + RT * Ginf * (Log(1 - x / Ginf) + (pL / (pL + 1)) * kL * ((x / Ginf) ^ (pL + 1)))
    Exit Function
End Select

End Function
