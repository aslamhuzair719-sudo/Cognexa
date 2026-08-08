import dns.resolver
import sys

def check_mx(domain):
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=10)
        hosts = sorted(((r.preference, str(r.exchange).rstrip('.')) for r in answers), key=lambda x: x[0])
        print('MX hosts:', hosts)
    except Exception as e:
        print('MX lookup failed:', type(e).__name__, e)
        sys.exit(1)

if __name__ == '__main__':
    check_mx('smhglobal.com.pk')
