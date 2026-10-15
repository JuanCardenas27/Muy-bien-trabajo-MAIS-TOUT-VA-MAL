// Genera web/src/contracts/generated.ts desde contracts/*.schema.json.
// Uso: npm run gen:types (se ejecuta desde web/).
// La salida pasa por prettier con la config de web/ para que `npm run lint`
// quede en verde; el resultado sigue siendo determinista.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { compile } from 'json-schema-to-typescript';
import prettier from 'prettier';

const CONTRACTS_DIR = new URL('../../contracts/', import.meta.url);
const OUT_FILE = new URL('../src/contracts/generated.ts', import.meta.url);

const SCHEMA_FILES = {
  content_index: 'content-index.schema.json',
  bundle_manifest: 'bundle-manifest.schema.json',
  pron_result: 'pron-result.schema.json',
};

const ROOT_REFS = {
  content_index: 'ContentIndex',
  bundle_manifest: 'BundleManifest',
  pron_result: 'PronResult',
};

function isDeepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

const mergedDefs = {};
for (const [prop, file] of Object.entries(SCHEMA_FILES)) {
  const schema = JSON.parse(
    await readFile(new URL(file, CONTRACTS_DIR), 'utf8'),
  );
  const { $defs = {}, title, ...root } = schema;
  delete root.$schema;
  if (title !== ROOT_REFS[prop]) {
    throw new Error(`title inesperado en ${file}: ${title}`);
  }
  if (mergedDefs[title] !== undefined) {
    throw new Error(`$def duplicado: ${title}`);
  }
  mergedDefs[title] = { title, ...root };
  for (const [name, def] of Object.entries($defs)) {
    if (mergedDefs[name] !== undefined && !isDeepEqual(mergedDefs[name], def)) {
      console.error(`Conflicto en $def "${name}" (viene de ${file})`);
      process.exit(1);
    }
    mergedDefs[name] = def;
  }
}

const wrapper = {
  title: 'FrancesContracts',
  type: 'object',
  properties: {
    content_index: { $ref: '#/$defs/ContentIndex' },
    bundle_manifest: { $ref: '#/$defs/BundleManifest' },
    pron_result: { $ref: '#/$defs/PronResult' },
  },
  $defs: mergedDefs,
};

const bannerComment =
  '/* GENERADO — no editar. Fuente: contracts/*.schema.json (npm run gen:types) */';

let ts = await compile(wrapper, 'FrancesContracts', {
  bannerComment,
  additionalProperties: false,
  unreachableDefinitions: true,
});

const prettierConfig = (await prettier.resolveConfig(OUT_FILE)) ?? {};
ts = await prettier.format(ts, { ...prettierConfig, parser: 'typescript' });

await mkdir(new URL('.', OUT_FILE), { recursive: true });
await writeFile(OUT_FILE, ts);
console.log(`Tipos generados en ${OUT_FILE.pathname}`);
