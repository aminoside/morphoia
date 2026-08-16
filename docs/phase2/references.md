# Références normatives et techniques de la Phase 2

## Politique de citation

La bibliographie scientifique, industrielle, brevets, thèses, projets et logiciels étudiés
est conservée dans le rapport de Phase 1. Le présent chapitre liste les sources directement
opposables aux choix de Phase 2 et évite de dupliquer cette revue. Une date de consultation
du 3 août 2026 s'applique aux pages web, sauf indication contraire.

Les textes ISO complets sont soumis aux conditions de leur éditeur. MORPHOIA cite les fiches
officielles et ne reproduit pas leur contenu normatif.

## ISO 10303 et STEP

1. ISO 10303-11:2004, *Industrial automation systems and integration - Product data
   representation and exchange - Part 11: Description methods: The EXPRESS language
   reference manual*. https://www.iso.org/standard/38047.html
2. ISO 10303-21, *Implementation methods: Clear text encoding of the exchange structure*.
   Catalogue ISO 10303.
3. ISO 10303-28, *Implementation methods: XML representations of EXPRESS schemas and data*.
   Catalogue ISO 10303.
4. ISO 10303-42, *Integrated generic resource: Geometric and topological representation*.
   Catalogue ISO 10303.
5. ISO 10303-55:2005, *Integrated generic resource: Procedural and hybrid representation*.
   https://www.iso.org/fr/standard/38226.html
6. ISO 10303-108:2005, *Integrated application resource: Parameterization and constraints for
   explicit geometric product models*. https://www.iso.org/standard/34697.html
7. ISO 10303-109, *Integrated application resource: Kinematic and geometric constraints for
   assembly models*. Catalogue ISO 10303.
8. ISO 10303-111:2007, *Integrated application resource: Elements for the procedural
   modelling of solid shapes*. https://www.iso.org/standard/39561.html
9. ISO 10303-112:2006, *Integrated application resource: Modelling commands for the exchange
   of procedurally represented 2D CAD models*. https://www.iso.org/standard/39581.html
10. ISO 10303-113:2025, *Integrated application resource: Mechanical product features*.
    https://www.iso.org/standard/91389.html
11. ISO 10303-203, *Application protocol: Configuration controlled 3D design of mechanical
    parts and assemblies*.
12. ISO 10303-214, *Application protocol: Core data for automotive mechanical design
    processes*.
13. ISO 10303-242:2025, édition 4, *Application protocol: Managed model-based 3D engineering*.
    https://www.iso.org/fr/standard/84300.html
14. ISO 10303-238, *Application protocol: Application interpreted model for computerized
    numerical controllers*.

## Autres standards et formats

15. ISO 14739, *Document management - 3D use of Product Representation Compact (PRC)
    format*.
16. ISO 14306, *Industrial automation systems and integration - JT file format specification
    for 3D visualization*.
17. ISO 16739-1, *Industry Foundation Classes (IFC) for data sharing in the construction and
    facility management industries*.
18. ASME Y14.5 et ISO GPS, spécifications dimensionnelles et tolérancement géométrique. Les
    éditions et profils applicables doivent être déclarés dans chaque implémentation.
19. Khronos Group, *glTF 2.0 Specification*.
    https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
20. Alliance for OpenUSD, *OpenUSD documentation and specifications*.
    https://openusd.org/release/index.html
21. buildingSMART International, *IFC specifications database*.
    https://technical.buildingsmart.org/standards/ifc/ifc-schema-specifications/

## Noyaux, CAO et SDK

22. Open CASCADE, *OCCT documentation*.
    https://dev.opencascade.org/doc/overview/html/
23. FreeCAD, *Developer documentation*.
    https://freecad.github.io/SourceDoc/
24. CadQuery, *Introduction* et *Selectors reference*.
    https://cadquery.readthedocs.io/en/latest/intro.html ;
    https://cadquery.readthedocs.io/en/stable/selectors.html
25. Onshape, *FeatureScript documentation*.
    https://cad.onshape.com/FsDoc/index.html
26. OpenSCAD, *User Manual*.
    https://openscad.org/documentation.html
27. Siemens Digital Industries Software, documentation publique Parasolid et JT.
28. Dassault Systèmes, documentation publique ACIS, CATIA et 3D InterOp.
29. Siemens, PTC, Dassault Systèmes, Autodesk et McNeel, documentations publiques de NX,
    Creo, SolidWorks, Fusion 360, Inventor et Rhino. Chaque adaptateur MORPHOIA doit citer la
    version exacte de l'API réellement qualifiée.
30. Tech Soft 3D HOOPS Exchange, CAD Exchanger et Datakit, documentations SDK publiques.

Les descriptions de Parasolid XT, ACIS SAT et formats CAO natifs ne constituent pas une
autorisation de redistribution. Les licences contractuelles et versions d'API priment sur
les pages marketing.

## Compilateurs et exécution

31. LLVM Project, *LLVM Language Reference Manual*.
    https://llvm.org/docs/LangRef.html
32. LLVM Project, *MLIR Language Reference*.
    https://mlir.llvm.org/docs/LangRef/
33. LLVM Project, *Defining Dialects* et *Defining Dialect Operations*.
    https://mlir.llvm.org/docs/DefiningDialects/ ;
    https://mlir.llvm.org/docs/DefiningDialects/Operations/
34. OpenXLA Project, documentation StableHLO et XLA.
    https://openxla.org/
35. ONNX, *Open Neural Network Exchange documentation*.
    https://onnx.ai/onnx/
36. ONNX Runtime, documentation d'exécution et fournisseurs matériels.
    https://onnxruntime.ai/docs/

## IA, vision et GPU

37. Vaswani et al., *Attention Is All You Need*, NeurIPS 2017.
38. Dosovitskiy et al., *An Image is Worth 16x16 Words*, ICLR 2021.
39. Ho et al., *Denoising Diffusion Probabilistic Models*, NeurIPS 2020.
40. Qi et al., *PointNet* et *PointNet++*, 2017.
41. NVIDIA, *CUDA C++ Programming Guide*.
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/
42. NVIDIA, *OptiX Programming Guide*.
    https://raytracing-docs.nvidia.com/optix8/guide/index.html
43. Khronos Group, *Vulkan Specification*.
    https://registry.khronos.org/vulkan/
44. AMD, *ROCm documentation*. https://rocm.docs.amd.com/
45. Khronos Group, *OpenCL specifications*. https://www.khronos.org/opencl/
46. Khronos Group, *SYCL specifications*. https://www.khronos.org/sycl/
47. Microsoft, *DirectML documentation*.
    https://learn.microsoft.com/windows/ai/directml/dml
48. NVIDIA, documentation Warp, Kaolin et PyTorch3D ; OpenVDB et NanoVDB pour les volumes.

Les études CAD génératives et de reconstruction - notamment SketchGraphs, DeepCAD,
Fusion 360 Gallery et les travaux B-rep/points récents - sont discutées et sourcées dans la
Phase 1. Leur utilisation future exige une vérification des licences, des splits de données,
des métriques et de la reproductibilité des modèles.

## Interopérabilité et archivage

49. CAX Implementor Forum, recommandations et campagnes d'interopérabilité STEP.
    https://www.cax-if.org/
50. LOTAR International, pratiques d'archivage long terme des données CAO.
    https://lotar-international.org/
51. NIST, travaux sur les propriétés de validation et l'interopérabilité MBD.
52. DMSC, *Quality Information Framework (QIF)*.
    https://qifstandards.org/

## Références propres à MORPHOIA

53. Louis Manhès et Olivier Ami, *MORPHOIA - Phase 1 : État de l'art et étude de faisabilité*, 2026.
54. MORPHOIA, `docs/phase2/requirements.md`, exigences héritées et critères de preuve.
55. MORPHOIA, `docs/phase2/decisions/`, ADR et modèle CJR.
56. MORPHOIA, `schemas/`, encodages expérimentaux de l'IR, des backends et des pertes.

Toute source ajoutée ultérieurement doit indiquer son éditeur, sa version ou date, son URL ou
identifiant pérenne, sa licence lorsque pertinente et l'exigence MORPHOIA qu'elle soutient.
