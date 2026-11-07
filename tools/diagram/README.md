# Diagram generator

`BionicPRO_C4_model_as-is.drawio.xml` is the course's as-is C4 container diagram, downloaded unchanged.

`gen_task1.py` builds the Task 1 to-be diagram from it: it keeps every as-is element, adds the per-country
access contour (BFF, session store, Keycloak and its database), the external directory and identity services,
the web application, and a second page with the BFF token flow as a sequence diagram.

```bash
python3 tools/diagram/gen_task1.py "Task1/BionicPRO_C4_container-diagram_to-be.drawio"
```

`render.py` renders every page of a draw.io file to PNG. There is no draw.io CLI on this machine, so each page is
embedded into a small HTML document that loads the public diagrams.net viewer script and headless Google Chrome
takes a screenshot of it (window size is derived from the page geometry, scale 1.5).

```bash
python3 tools/diagram/render.py "Task1/BionicPRO_C4_container-diagram_to-be.drawio" Task1/render
```
