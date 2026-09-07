#!/usr/bin/env bash
# Resolve the three tools the runner needs into TOOLS_DIR, and write tools.env
# with absolute paths for run_pair.py to source.
#
#   bash setup_tools.sh [TOOLS_DIR]      (default: ./tools)
#
# Everything comes through Maven, so nothing is vendored into the repository.
#   jacocoagent.jar   the -javaagent, attached to the single-test JVM
#   jacococli.jar     turns jacoco.exec into coverage.xml
#   spoon_cp.txt      full Spoon classpath (spoon-core plus its transitive deps;
#                     spoon-core alone is not enough, it needs JDT at runtime)

set -euo pipefail
TOOLS="${1:-tools}"
JACOCO_VERSION="${JACOCO_VERSION:-0.8.11}"
SPOON_VERSION="${SPOON_VERSION:-10.4.2}"
mkdir -p "$TOOLS"

echo "== JaCoCo $JACOCO_VERSION =="
mvn -B -q dependency:get -Dartifact="org.jacoco:org.jacoco.agent:$JACOCO_VERSION:jar:runtime"
mvn -B -q dependency:get -Dartifact="org.jacoco:org.jacoco.cli:$JACOCO_VERSION:jar:nodeps"

M2="${M2_REPO:-$HOME/.m2/repository}"
AGENT="$M2/org/jacoco/org.jacoco.agent/$JACOCO_VERSION/org.jacoco.agent-$JACOCO_VERSION-runtime.jar"
CLI="$M2/org/jacoco/org.jacoco.cli/$JACOCO_VERSION/org.jacoco.cli-$JACOCO_VERSION-nodeps.jar"
cp "$AGENT" "$TOOLS/jacocoagent.jar"
cp "$CLI"   "$TOOLS/jacococli.jar"

echo "== Spoon $SPOON_VERSION =="
# A throwaway POM is the least fragile way to get the transitive classpath;
# dependency:build-classpath needs a project to resolve against.
mkdir -p "$TOOLS/_spoon"
cat > "$TOOLS/_spoon/pom.xml" <<POM
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>flakylens</groupId><artifactId>spoon-cp</artifactId><version>1.0</version>
  <properties>
    <maven.compiler.source>11</maven.compiler.source>
    <maven.compiler.target>11</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>fr.inria.gforge.spoon</groupId>
      <artifactId>spoon-core</artifactId><version>$SPOON_VERSION</version>
    </dependency>
  </dependencies>
</project>
POM
# Absolute paths must be readable by BOTH the shell and the JVM/Python that
# consume them. Under Git Bash `pwd` yields /c/... or /tmp/..., which Windows
# Python cannot open, so translate when cygpath is available.
if command -v cygpath >/dev/null 2>&1; then
  ABS="$(cygpath -m "$(cd "$TOOLS" && pwd)")"
else
  ABS="$(cd "$TOOLS" && pwd)"
fi

mvn -B -q -f "$TOOLS/_spoon/pom.xml" dependency:build-classpath \
    -Dmdep.outputFile="$ABS/spoon_cp.txt" -Dmdep.includeScope=runtime

# tools.env holds absolute paths; run_pair.py is invoked from many directories.
cat > "$TOOLS/tools.env" <<ENV
JACOCO_AGENT=$ABS/jacocoagent.jar
JACOCO_CLI=$ABS/jacococli.jar
SPOON_CP_FILE=$ABS/spoon_cp.txt
JACOCO_VERSION=$JACOCO_VERSION
ENV

echo
ls -la "$TOOLS"/jacoco*.jar "$TOOLS"/spoon_cp.txt "$TOOLS"/tools.env
echo "spoon classpath entries: $(tr ';:' '\n\n' < "$TOOLS/spoon_cp.txt" | grep -c jar || true)"
