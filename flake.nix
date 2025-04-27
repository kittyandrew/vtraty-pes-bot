{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = {
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs {inherit system;};
        pythonCustom = pkgs.python3.withPackages (ps:
          with ps; [
            # Setup utils for packages and builds.
            pip
            wheel
            packaging
            setuptools
            # @TODO: Replace this with nix shell stuff.
            virtualenv # Local pythonic dev-env management.
            # Static analysis and formatting packages.
            flake8
            mypy
            black
            isort
          ]);
        libs = with pkgs; [
          stdenv.cc.cc
          zlib
          glib
          libGL
        ];
      in {
        devShell = pkgs.mkShell {
          buildInputs = [
            # Installing our custom python with pre-installed packages.
            pythonCustom
            pkgs.wkhtmltopdf
            pkgs.ffmpeg
          ];
          # Upon installation we need to do additional configurations.
          shellHook = ''
            # Some python packages do RUNTIME DL loading from the provided paths, sigh.
            export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libs}

            # We want to install additional requirements into a virtual env [for now].
            if [[ -f requirements.txt ]]; then
              if [[ -d .venv ]]; then
                echo "Verifying virtual environment is setup with all packages.."
                # @NOTE: In happy-case it is much cleaner to suppress the output. Is it bad? IDK.
                python -m virtualenv -q .venv && source .venv/bin/activate
                python -m pip install -qr requirements.txt
              else
                # There is no point in echo-ing here, normal pip log is super verbose.
                python -m virtualenv .venv && source .venv/bin/activate
                python -m pip install -r requirements.txt
              fi
            fi

            pyfmt() {
              black --line-length=131 $@
              isort --line-length=131 $@
              # flake8 $@
            }

            echo -e "\nWelcome to the shell :)\n"
          '';
        };
      }
    );
}
