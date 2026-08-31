{
  description = "synapsen — ein homöostatischer Zustandskern für Agenten";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        synapsen = python.pkgs.buildPythonPackage {
          pname = "synapsen";
          version = "0.1.0";
          format = "pyproject";
          src = ./.;

          nativeBuildInputs = [ python.pkgs.hatchling ];

          # Bewusst leer: das Paket nutzt ausschließlich die Standardbibliothek.
          propagatedBuildInputs = [ ];

          nativeCheckInputs = [ python.pkgs.pytest ];
          checkPhase = ''
            runHook preCheck
            ${python.pkgs.pytest}/bin/pytest -q
            runHook postCheck
          '';

          pythonImportsCheck = [ "synapsen" ];

          meta = with pkgs.lib; {
            description = "Homöostatischer Zustandskern für Agenten";
            homepage = "https://github.com/Xarksus/synapsen";
            license = licenses.asl20;
            mainProgram = "synapsen";
          };
        };
      in
      {
        packages.default = synapsen;
        packages.synapsen = synapsen;

        apps.default = flake-utils.lib.mkApp { drv = synapsen; };

        # Der MCP-Server als eigener Einstiegspunkt, praktisch für
        # `services.…` oder einen systemd-User-Dienst.
        apps.mcp = {
          type = "app";
          program = "${synapsen}/bin/synapsen-mcp";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (ps: [ ps.pytest ps.hatchling ]))
            pkgs.ruff
          ];
          shellHook = ''
            echo "synapsen — Entwicklungsumgebung"
            echo "  pytest -q          Tests"
            echo "  ruff check .       Linter"
            echo "  python -m synapsen.cli doctor"
          '';
        };
      });
}
