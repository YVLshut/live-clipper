import { useStore } from "../store";
import { ExtLink, Modal } from "./ui";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-4">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full gradient-bg text-sm font-semibold text-white">{n}</span>
      <div className="pb-5">
        <p className="font-medium text-ink-100">{title}</p>
        <div className="mt-1 space-y-1.5 text-sm text-ink-300">{children}</div>
      </div>
    </li>
  );
}

const Code = ({ children }: { children: React.ReactNode }) => <code className="rounded bg-ink-900 px-1.5 py-0.5 text-[12px] text-ink-100 select-all">{children}</code>;

export function DevGuide({ platform, onClose }: { platform: "instagram" | "tiktok"; onClose: () => void }) {
  const settings = useStore((s) => s.settings);
  const redirect = settings?.oauth_redirects[platform] ?? "";
  return (
    <Modal open onClose={onClose} title={platform === "instagram" ? "Créer ton app Meta (Instagram)" : "Créer ton app TikTok"} width="max-w-3xl">
      {platform === "instagram" ? (
        <ol>
          <Step n={1} title="Prépare ton compte Instagram">
            <p>Passe ton compte en <b>compte professionnel</b> (Créateur ou Entreprise) dans l'app Instagram : Paramètres → Type de compte.</p>
            <p>Relie-le à une <b>Page Facebook</b> (Paramètres de la Page → Comptes liés → Instagram).</p>
          </Step>
          <Step n={2} title="Crée un compte développeur Meta">
            <p>
              Va sur <ExtLink href="https://developers.facebook.com/apps">developers.facebook.com/apps</ExtLink> et connecte-toi avec le compte Facebook qui gère la Page.
            </p>
          </Step>
          <Step n={3} title="Crée une app">
            <p>« Créer une app » → cas d'usage <b>« Autre »</b> → type <b>« Entreprise »</b>. Donne-lui un nom (ex : Live Clipper perso).</p>
          </Step>
          <Step n={4} title="Ajoute les produits">
            <p>
              Ajoute <b>Facebook Login</b> et <b>API Instagram Graph</b>. Dans Facebook Login → Paramètres, colle l'URL de redirection OAuth valide :
            </p>
            <p>
              <Code>{redirect}</Code>
            </p>
          </Step>
          <Step n={5} title="Ajoute-toi comme testeur">
            <p>
              Rôles de l'app → Rôles : ton compte Facebook est administrateur. L'app peut rester en <b>mode Développement</b> pour publier sur tes propres comptes.
            </p>
            <p>
              Autorisations demandées : <Code>instagram_basic</Code> <Code>instagram_content_publish</Code> <Code>pages_show_list</Code> <Code>pages_read_engagement</Code> <Code>business_management</Code>.
            </p>
          </Step>
          <Step n={6} title="Copie les identifiants">
            <p>Paramètres de l'app → Général : copie l'<b>ID de l'app</b> et la <b>clé secrète</b> dans les Paramètres de Live Clipper, puis enregistre.</p>
          </Step>
          <Step n={7} title="Connecte ton compte">
            <p>Onglet Comptes → « Ajouter un compte » → Instagram → mode API → « Se connecter ». Une fenêtre Facebook s'ouvre dans ton navigateur : accepte les autorisations.</p>
          </Step>
        </ol>
      ) : (
        <ol>
          <Step n={1} title="Crée un compte développeur TikTok">
            <p>
              Va sur <ExtLink href="https://developers.tiktok.com/">developers.tiktok.com</ExtLink> et connecte-toi (« Manage apps »).
            </p>
          </Step>
          <Step n={2} title="Crée une app">
            <p>« Connect an app » → renseigne le nom, l'icône et la catégorie. Choisis la plateforme <b>Desktop</b> (sinon Web).</p>
          </Step>
          <Step n={3} title="Ajoute les produits">
            <p>
              Ajoute <b>Login Kit</b> et <b>Content Posting API</b> (active « Direct Post »). Scopes : <Code>user.info.basic</Code> <Code>video.publish</Code> <Code>video.upload</Code>.
            </p>
          </Step>
          <Step n={4} title="Déclare l'URL de redirection">
            <p>Dans Login Kit, ajoute :</p>
            <p>
              <Code>{redirect}</Code>
            </p>
            <p className="text-amber-300">
              Si TikTok refuse une adresse locale (il exige parfois HTTPS pour les apps Web), déclare une URL HTTPS de ton choix : Live Clipper te proposera alors de coller l'adresse de la page de retour pour terminer la connexion.
            </p>
          </Step>
          <Step n={5} title="Mode Sandbox et audit">
            <p>
              Ajoute ton compte TikTok comme <b>utilisateur cible</b> du Sandbox. Tant que l'app n'a pas passé l'<b>audit TikTok</b>, les vidéos sont publiées en <b>privé</b> (visibles par toi seul) : tu peux ensuite les passer en public depuis l'app TikTok.
            </p>
          </Step>
          <Step n={6} title="Copie les identifiants">
            <p>Copie la <b>Client key</b> et le <b>Client secret</b> dans les Paramètres de Live Clipper, puis enregistre.</p>
          </Step>
          <Step n={7} title="Connecte ton compte">
            <p>Onglet Comptes → « Ajouter un compte » → TikTok → mode API → « Se connecter ».</p>
          </Step>
        </ol>
      )}
    </Modal>
  );
}
